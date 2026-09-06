"""VIA GPIO playground: a panel for observing and driving every pin of a via/6522 device.

Connects to a `via/6522` device's `unix:` transport and speaks the VIA peer
protocol's ASCII encoding via `emma65_via`. Port A's data pins (PA0-PA7) and
Port B's (PB0-PB5; PB6/PB7 are Units 8-9) are fully interactive: clicking a
toggle flips that pin's local-pull state and clicking-and-holding a
momentary button asserts the opposite level for the duration of the press
(see `PortIO`/`Peripheral`). The chevron's fill continues to track live
pin-level events from the VIA; direction stays a declared, panel-side
setting (`--pa-direction`/`--pb-direction`) since the protocol never conveys
DDR. CA1/CA2/CB1/CB2 are momentary-only control lines: level mode drives the
active edge for as long as the button is held, pulse mode fires one
fixed-duration transition per press regardless of hold time, and polarity
picks which edge (rising/falling) counts as "active" (see `ControlPinState`).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import pygame

from emma65_via import PortBitsReset, PortBitsSet, PortState, ViaAsciiClient

from . import cells

DEFAULT_SOCKET = "~/.emma/sock/via6522"
DEFAULT_PA_DIRECTION = 0xF0
DEFAULT_PB_DIRECTION = 0x38
RECONNECT_INTERVAL_MS = 1000
CTRL_PULSE_DURATION_MS = 100

FOOTER_H = cells.sc(24)
CONNECTED_COLOR = (120, 200, 140)
DISCONNECTED_COLOR = (210, 100, 100)


def _hex_byte(s: str) -> int:
    try:
        value = int(s, 16)
    except ValueError:
        value = -1
    if not 0 <= value <= 0xFF:
        raise argparse.ArgumentTypeError(f"must be a hex byte 00-FF, got {s!r}")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--socket", default=DEFAULT_SOCKET,
        help=f"Unix-domain socket path for the VIA transport (default: {DEFAULT_SOCKET})",
    )
    parser.add_argument(
        "--pa-direction", type=_hex_byte, default=DEFAULT_PA_DIRECTION, metavar="HEX",
        help="Declared DDRA value for Port A data pins, as a hex byte -- bit n set means "
        f"PAn is an output (default: {DEFAULT_PA_DIRECTION:02X}, i.e. PA7-PA4 out, PA3-PA0 "
        "in). The VIA peer protocol never reports DDR, so this must be set to match the "
        "firmware's actual configuration; a mismatch shows up as pin-level/chevron "
        "divergence rather than an error.",
    )
    parser.add_argument(
        "--pb-direction", type=_hex_byte, default=DEFAULT_PB_DIRECTION, metavar="HEX",
        help="Declared DDRB value for Port B data pins PB0-PB5, as a hex byte -- bit n set "
        f"means PBn is an output (default: {DEFAULT_PB_DIRECTION:02X}, i.e. PB5-PB3 out, "
        "PB2-PB0 in). Bits 6-7 are ignored (PB6/PB7 aren't in scope yet). Same DDR caveat "
        "as --pa-direction applies.",
    )
    return parser.parse_args(argv)


@dataclass
class ControlPinState:
    """Local state for one control pin (CA1/CA2): mode, polarity, press state.

    Control lines have no toggle-driven "local pull" the way data pins do
    (per the design doc, they're momentary-only) -- instead, `polarity`
    determines the idle level (rising = idle low, falling = idle high, per
    checkpoint 1's pulse-graph icon semantics), and pressing the momentary
    asserts the opposite ("active") level.
    """

    mode: cells.Mode = "level"
    polarity: cells.Polarity = "rising"
    held: bool = False
    pulse_release_at: int | None = None

    def idle_level(self) -> bool:
        return self.polarity == "falling"

    def driven_level(self) -> bool:
        if self.pulse_release_at is not None:
            return not self.idle_level()
        if self.mode == "level" and self.held:
            return not self.idle_level()
        return self.idle_level()


@dataclass
class PortIO:
    """Local write-state for one port's data bits and two control pins.

    `num_bits` is how many data lines this panel owns on this port (8 for
    Port A, 6 for Port B since PB6/PB7 aren't in scope until Units 8-9) --
    it bounds reconnect re-assertion so the panel never sends a bit it
    doesn't own.

    `local` is the toggle position bitmask (bit set = pulling high) -- the
    LED and toggle widgets reflect this directly. `momentary` is which bits
    currently have their momentary button held, which asserts the
    *opposite* of the toggle's level for the duration of the press
    (mirroring `emma65_buttons.ButtonPeripheral.toggle`/`_send_bit`,
    generalized from one hardcoded bit to 8 independent ones, and now to
    more than one port). `level` is the live pin level read back from the
    VIA. `ctrl` maps control-pin number (1 or 2) to its `ControlPinState`.
    """

    num_bits: int = 8
    level: int = 0
    local: int = 0
    momentary: int = 0
    ctrl: dict[int, ControlPinState] = field(default_factory=lambda: {1: ControlPinState(), 2: ControlPinState()})

    def driven_level(self, bit: int) -> bool:
        mask = 1 << bit
        local = bool(self.local & mask)
        return not local if self.momentary & mask else local


class Peripheral:
    """Owns the VIA connection and every port's data bits and control-pin state.

    This peripheral owns all of each configured port's data lines and both
    of its control pins by design (it isn't sharing a port with another
    peripheral instance), so each `PortIO` tracks every data bit up to its
    `num_bits` and both control pins rather than a configured subset.
    """

    def __init__(self, args: argparse.Namespace):
        self._client = ViaAsciiClient(args.socket)
        self._next_connect_attempt = 0
        self.ports: dict[str, PortIO] = {"A": PortIO(num_bits=8), "B": PortIO(num_bits=6)}

    @property
    def connected(self) -> bool:
        return self._client.connected

    def connect_if_needed(self, now_ms: int) -> None:
        if self._client.connected or now_ms < self._next_connect_attempt:
            return
        if self._client.connect():
            # Re-assert every bit's/control pin's driven level so mid-
            # press/toggle state survives a reconnect.
            for port, io in self.ports.items():
                for bit in range(io.num_bits):
                    self._send_bit(port, bit, io.driven_level(bit))
                for pin, state in io.ctrl.items():
                    self._send_ctrl(port, pin, state.driven_level())
        else:
            self._next_connect_attempt = now_ms + RECONNECT_INTERVAL_MS

    def poll(self) -> None:
        if not self._client.connected:
            return
        try:
            events = self._client.poll()
        except ConnectionError:
            return  # connect_if_needed() will notice and retry
        for event in events:
            self._handle_event(event)

    def _handle_event(self, event) -> None:
        if not isinstance(event, (PortState, PortBitsSet, PortBitsReset)):
            return
        io = self.ports.get(event.port)
        if io is None:
            return
        if isinstance(event, PortState):
            io.level = event.level
        elif isinstance(event, PortBitsSet):
            io.level |= event.mask
        else:
            io.level &= ~event.mask & 0xFF

    def toggle_data(self, port: str, bit: int) -> None:
        """Flips `bit`'s toggle position on `port` and re-sends its driven level (unless a
        momentary press on the same bit is currently overriding it)."""
        io = self.ports[port]
        mask = 1 << bit
        io.local ^= mask
        if not io.momentary & mask:
            self._send_bit(port, bit, io.driven_level(bit))

    def set_momentary(self, port: str, bit: int, pressed: bool) -> None:
        """Presses or releases `bit`'s momentary button on `port`, re-sending its driven level."""
        io = self.ports[port]
        mask = 1 << bit
        if pressed == bool(io.momentary & mask):
            return
        if pressed:
            io.momentary |= mask
        else:
            io.momentary &= ~mask
        self._send_bit(port, bit, io.driven_level(bit))

    def _send_bit(self, port: str, bit: int, level: bool) -> None:
        if not self._client.connected:
            return
        mask = 1 << bit
        try:
            if level:
                self._client.set_bits(port, mask)
            else:
                self._client.reset_bits(port, mask)
        except ConnectionError:
            pass  # connect_if_needed() will notice and retry

    def press_ctrl(self, port: str, pin: int, now_ms: int) -> None:
        """Presses `pin`'s momentary button on `port`.

        Level mode drives the active (polarity-selected) level for as long
        as the button stays held. Pulse mode fires one fixed-duration
        transition regardless of hold time -- `update_ctrl_pulses` reverts
        it to idle once `CTRL_PULSE_DURATION_MS` has elapsed. Pressing again
        mid-pulse restarts the timer rather than stacking pulses.
        """
        state = self.ports[port].ctrl[pin]
        state.held = True
        if state.mode == "pulse":
            state.pulse_release_at = now_ms + CTRL_PULSE_DURATION_MS
        self._send_ctrl(port, pin, not state.idle_level())

    def release_ctrl(self, port: str, pin: int) -> None:
        """Releases `pin`'s momentary button on `port`.

        In level mode this returns the pin to idle immediately. In pulse
        mode the level is already scheduled to revert via
        `update_ctrl_pulses`, so an early release doesn't change the wire.
        """
        state = self.ports[port].ctrl[pin]
        state.held = False
        if state.mode == "level":
            self._send_ctrl(port, pin, state.idle_level())

    def update_ctrl_pulses(self, now_ms: int) -> None:
        """Reverts any control pin (on any port) whose fixed-duration pulse has elapsed back to idle."""
        for port, io in self.ports.items():
            for pin, state in io.ctrl.items():
                if state.pulse_release_at is not None and now_ms >= state.pulse_release_at:
                    state.pulse_release_at = None
                    self._send_ctrl(port, pin, state.idle_level())

    def toggle_ctrl_mode(self, port: str, pin: int) -> None:
        """Flips `pin` on `port` between pulse and level mode.

        Cancels any in-flight pulse and re-asserts idle -- the momentary
        can't be held at the same time a mouse click is toggling this
        setting, so `held` is never true here in practice, but clearing the
        pulse timer avoids leaving a stale scheduled revert around.
        """
        state = self.ports[port].ctrl[pin]
        state.mode = "level" if state.mode == "pulse" else "pulse"
        if state.pulse_release_at is not None:
            state.pulse_release_at = None
            self._send_ctrl(port, pin, state.idle_level())

    def toggle_ctrl_polarity(self, port: str, pin: int) -> None:
        """Flips `pin`'s idle/active polarity on `port`, re-asserting idle level if not currently active."""
        state = self.ports[port].ctrl[pin]
        state.polarity = "falling" if state.polarity == "rising" else "rising"
        if not state.held and state.pulse_release_at is None:
            self._send_ctrl(port, pin, state.idle_level())

    def _send_ctrl(self, port: str, pin: int, level: bool) -> None:
        if not self._client.connected:
            return
        try:
            if level:
                self._client.set_ctrl_pin(port, pin)
            else:
                self._client.reset_ctrl_pin(port, pin)
        except ConnectionError:
            pass  # connect_if_needed() will notice and retry

    def close(self) -> None:
        self._client.close()


def run(args: argparse.Namespace) -> None:
    pygame.init()
    pygame.display.set_caption("emma65 VIA GPIO playground")

    ports = [cells.build_port_a(args.pa_direction), cells.build_port_b(args.pb_direction)]
    content_right = cells.layout_ports(ports, 0)
    window_size = (
        cells.LEFT_MARGIN + content_right + cells.LEFT_MARGIN,
        cells.CONTENT_HEIGHT + FOOTER_H,
    )
    screen = pygame.display.set_mode(window_size)
    cells.layout_ports(ports, cells.LEFT_MARGIN)

    clock = pygame.time.Clock()
    fonts = cells.Fonts()

    peripheral = Peripheral(args)
    all_cells = [cell for port in ports for cell in port]
    data_cells = [cell for cell in all_cells if isinstance(cell, cells.DataCell) and cell.bit is not None]
    ctrl_cells = [cell for cell in all_cells if isinstance(cell, cells.ControlCell) and cell.ctrl_pin is not None]
    pressed_momentary: tuple[str, int] | None = None
    pressed_ctrl: tuple[str, int] | None = None

    running = True
    while running:
        now_ms = pygame.time.get_ticks()
        peripheral.connect_if_needed(now_ms)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for cell in data_cells:
                    if cell.toggle_rect().collidepoint(event.pos):
                        peripheral.toggle_data(cell.port, cell.bit)
                        break
                    if cell.momentary_rect().collidepoint(event.pos):
                        peripheral.set_momentary(cell.port, cell.bit, True)
                        pressed_momentary = (cell.port, cell.bit)
                        break
                else:
                    for cell in ctrl_cells:
                        if cell.mode_rect().collidepoint(event.pos):
                            peripheral.toggle_ctrl_mode(cell.port, cell.ctrl_pin)
                            break
                        if cell.polarity_rect().collidepoint(event.pos):
                            peripheral.toggle_ctrl_polarity(cell.port, cell.ctrl_pin)
                            break
                        if cell.momentary_rect().collidepoint(event.pos):
                            peripheral.press_ctrl(cell.port, cell.ctrl_pin, now_ms)
                            pressed_ctrl = (cell.port, cell.ctrl_pin)
                            break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if pressed_momentary is not None:
                    peripheral.set_momentary(*pressed_momentary, False)
                    pressed_momentary = None
                if pressed_ctrl is not None:
                    peripheral.release_ctrl(*pressed_ctrl)
                    pressed_ctrl = None

        peripheral.update_ctrl_pulses(now_ms)
        peripheral.poll()
        for cell in data_cells:
            io = peripheral.ports[cell.port]
            cell.pin = bool((io.level >> cell.bit) & 1)
            cell.local = bool((io.local >> cell.bit) & 1)
            cell.momentary_pressed = bool((io.momentary >> cell.bit) & 1)
        for cell in ctrl_cells:
            state = peripheral.ports[cell.port].ctrl[cell.ctrl_pin]
            cell.mode = state.mode
            cell.polarity = state.polarity
            cell.momentary_pressed = state.held

        screen.fill(cells.BG)
        cells.draw_status_bar(screen, fonts, "PORT A / PORT B", window_size[0])
        for cell in all_cells:
            cell.draw(screen, fonts)

        status = "connected" if peripheral.connected else "connecting..."
        color = CONNECTED_COLOR if peripheral.connected else DISCONNECTED_COLOR
        cells.draw_text(
            screen, fonts.ui_small, f"{status}  ({args.socket})", color,
            topleft=(cells.LEFT_MARGIN, cells.CONTENT_HEIGHT + cells.sc(4)),
        )

        pygame.display.flip()
        clock.tick(60)

    peripheral.close()
    pygame.quit()


def main(argv: list[str] | None = None) -> None:
    run(parse_args(sys.argv[1:] if argv is None else argv))
