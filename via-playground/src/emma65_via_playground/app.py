"""VIA GPIO playground: a panel for observing and driving every pin of a via/6522 device.

Connects to a `via/6522` device's `unix:` transport and speaks the VIA peer
protocol's ASCII encoding via `emma65_via`. Port A's data pins (PA0-PA7) are
fully interactive: clicking a toggle flips that pin's local-pull state and
clicking-and-holding a momentary button asserts the opposite level for the
duration of the press (see `Peripheral`). The chevron's fill continues to
track live pin-level events from the VIA; direction stays a declared,
panel-side setting (`--pa-direction`) since the protocol never conveys DDR.
CA1/CA2 are momentary-only control lines: level mode drives the active edge
for as long as the button is held, pulse mode fires one fixed-duration
transition per press regardless of hold time, and polarity picks which edge
(rising/falling) counts as "active" (see `ControlPinState`).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import pygame

from emma65_via import PortBitsReset, PortBitsSet, PortState, ViaAsciiClient

from . import cells

DEFAULT_SOCKET = "~/.emma/sock/via6522"
DEFAULT_PA_DIRECTION = 0xF0
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


class Peripheral:
    """Owns the VIA connection, Port A's 8 data bits, and CA1/CA2's control state.

    This peripheral owns all 8 of Port A's data lines and both of its control
    pins by design (it isn't sharing the port with another peripheral
    instance), so `pa_local`/`pa_momentary` track every data bit and `ca`
    covers both control pins rather than a configured subset.

    `pa_local` is the toggle position per bit (bit set = pulling high) --
    the LED and toggle widgets reflect this directly. `pa_momentary` is
    which bits currently have their momentary button held, which asserts
    the *opposite* of the toggle's level for the duration of the press
    (mirroring `emma65_buttons.ButtonPeripheral.toggle`/`_send_bit`,
    generalized from one hardcoded bit to 8 independent ones).

    `ca` maps control-pin number (1 or 2) to its `ControlPinState`.
    """

    def __init__(self, args: argparse.Namespace):
        self._client = ViaAsciiClient(args.socket)
        self._next_connect_attempt = 0
        self.port_a_level = 0
        self.pa_local = 0
        self.pa_momentary = 0
        self.ca: dict[int, ControlPinState] = {1: ControlPinState(), 2: ControlPinState()}

    @property
    def connected(self) -> bool:
        return self._client.connected

    def connect_if_needed(self, now_ms: int) -> None:
        if self._client.connected or now_ms < self._next_connect_attempt:
            return
        if self._client.connect():
            # Re-assert every bit's/control pin's driven level so mid-
            # press/toggle state survives a reconnect.
            for bit in range(8):
                self._send_bit(bit, self._driven_level(bit))
            for pin, state in self.ca.items():
                self._send_ctrl(pin, state.driven_level())
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
        if isinstance(event, PortState) and event.port == "A":
            self.port_a_level = event.level
        elif isinstance(event, PortBitsSet) and event.port == "A":
            self.port_a_level |= event.mask
        elif isinstance(event, PortBitsReset) and event.port == "A":
            self.port_a_level &= ~event.mask & 0xFF

    def toggle_pa(self, bit: int) -> None:
        """Flips `bit`'s toggle position and re-sends its driven level (unless a
        momentary press on the same bit is currently overriding it)."""
        mask = 1 << bit
        self.pa_local ^= mask
        if not self.pa_momentary & mask:
            self._send_bit(bit, self._driven_level(bit))

    def set_pa_momentary(self, bit: int, pressed: bool) -> None:
        """Presses or releases `bit`'s momentary button, re-sending its driven level."""
        mask = 1 << bit
        if pressed == bool(self.pa_momentary & mask):
            return
        if pressed:
            self.pa_momentary |= mask
        else:
            self.pa_momentary &= ~mask
        self._send_bit(bit, self._driven_level(bit))

    def _driven_level(self, bit: int) -> bool:
        mask = 1 << bit
        local = bool(self.pa_local & mask)
        return not local if self.pa_momentary & mask else local

    def _send_bit(self, bit: int, level: bool) -> None:
        if not self._client.connected:
            return
        mask = 1 << bit
        try:
            if level:
                self._client.set_bits("A", mask)
            else:
                self._client.reset_bits("A", mask)
        except ConnectionError:
            pass  # connect_if_needed() will notice and retry

    def press_ctrl(self, pin: int, now_ms: int) -> None:
        """Presses `pin`'s momentary button.

        Level mode drives the active (polarity-selected) level for as long
        as the button stays held. Pulse mode fires one fixed-duration
        transition regardless of hold time -- `update_ctrl_pulses` reverts
        it to idle once `CTRL_PULSE_DURATION_MS` has elapsed. Pressing again
        mid-pulse restarts the timer rather than stacking pulses.
        """
        state = self.ca[pin]
        state.held = True
        if state.mode == "pulse":
            state.pulse_release_at = now_ms + CTRL_PULSE_DURATION_MS
        self._send_ctrl(pin, not state.idle_level())

    def release_ctrl(self, pin: int) -> None:
        """Releases `pin`'s momentary button.

        In level mode this returns the pin to idle immediately. In pulse
        mode the level is already scheduled to revert via
        `update_ctrl_pulses`, so an early release doesn't change the wire.
        """
        state = self.ca[pin]
        state.held = False
        if state.mode == "level":
            self._send_ctrl(pin, state.idle_level())

    def update_ctrl_pulses(self, now_ms: int) -> None:
        """Reverts any control pin whose fixed-duration pulse has elapsed back to idle."""
        for pin, state in self.ca.items():
            if state.pulse_release_at is not None and now_ms >= state.pulse_release_at:
                state.pulse_release_at = None
                self._send_ctrl(pin, state.idle_level())

    def toggle_ctrl_mode(self, pin: int) -> None:
        """Flips `pin` between pulse and level mode.

        Cancels any in-flight pulse and re-asserts idle -- the momentary
        can't be held at the same time a mouse click is toggling this
        setting, so `held` is never true here in practice, but clearing the
        pulse timer avoids leaving a stale scheduled revert around.
        """
        state = self.ca[pin]
        state.mode = "level" if state.mode == "pulse" else "pulse"
        if state.pulse_release_at is not None:
            state.pulse_release_at = None
            self._send_ctrl(pin, state.idle_level())

    def toggle_ctrl_polarity(self, pin: int) -> None:
        """Flips `pin`'s idle/active polarity, re-asserting idle level if not currently active."""
        state = self.ca[pin]
        state.polarity = "falling" if state.polarity == "rising" else "rising"
        if not state.held and state.pulse_release_at is None:
            self._send_ctrl(pin, state.idle_level())

    def _send_ctrl(self, pin: int, level: bool) -> None:
        if not self._client.connected:
            return
        try:
            if level:
                self._client.set_ctrl_pin("A", pin)
            else:
                self._client.reset_ctrl_pin("A", pin)
        except ConnectionError:
            pass  # connect_if_needed() will notice and retry

    def close(self) -> None:
        self._client.close()


def run(args: argparse.Namespace) -> None:
    pygame.init()
    pygame.display.set_caption("emma65 VIA GPIO playground")

    port_a = cells.build_port_a(args.pa_direction)
    content_right = cells.layout_row(port_a, 0)
    window_size = (
        cells.LEFT_MARGIN + content_right + cells.LEFT_MARGIN,
        cells.CONTENT_HEIGHT + FOOTER_H,
    )
    screen = pygame.display.set_mode(window_size)
    cells.layout_row(port_a, cells.LEFT_MARGIN)

    clock = pygame.time.Clock()
    fonts = cells.Fonts()

    peripheral = Peripheral(args)
    data_cells = [cell for cell in port_a if isinstance(cell, cells.DataCell) and cell.bit is not None]
    ctrl_cells = [cell for cell in port_a if isinstance(cell, cells.ControlCell) and cell.ctrl_pin is not None]
    pressed_momentary_bit: int | None = None
    pressed_ctrl_pin: int | None = None

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
                        peripheral.toggle_pa(cell.bit)
                        break
                    if cell.momentary_rect().collidepoint(event.pos):
                        peripheral.set_pa_momentary(cell.bit, True)
                        pressed_momentary_bit = cell.bit
                        break
                else:
                    for cell in ctrl_cells:
                        if cell.mode_rect().collidepoint(event.pos):
                            peripheral.toggle_ctrl_mode(cell.ctrl_pin)
                            break
                        if cell.polarity_rect().collidepoint(event.pos):
                            peripheral.toggle_ctrl_polarity(cell.ctrl_pin)
                            break
                        if cell.momentary_rect().collidepoint(event.pos):
                            peripheral.press_ctrl(cell.ctrl_pin, now_ms)
                            pressed_ctrl_pin = cell.ctrl_pin
                            break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if pressed_momentary_bit is not None:
                    peripheral.set_pa_momentary(pressed_momentary_bit, False)
                    pressed_momentary_bit = None
                if pressed_ctrl_pin is not None:
                    peripheral.release_ctrl(pressed_ctrl_pin)
                    pressed_ctrl_pin = None

        peripheral.update_ctrl_pulses(now_ms)
        peripheral.poll()
        for cell in data_cells:
            cell.pin = bool((peripheral.port_a_level >> cell.bit) & 1)
            cell.local = bool((peripheral.pa_local >> cell.bit) & 1)
            cell.momentary_pressed = bool((peripheral.pa_momentary >> cell.bit) & 1)
        for cell in ctrl_cells:
            state = peripheral.ca[cell.ctrl_pin]
            cell.mode = state.mode
            cell.polarity = state.polarity
            cell.momentary_pressed = state.held

        screen.fill(cells.BG)
        cells.draw_status_bar(screen, fonts, "PORT A", window_size[0])
        for cell in port_a:
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
