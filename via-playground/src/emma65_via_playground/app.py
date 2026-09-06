"""VIA GPIO playground: a panel for observing and driving every pin of a via/6522 device.

Connects to a `via/6522` device's `unix:` transport and speaks the VIA peer
protocol's ASCII encoding via `emma65_via`. Port A's data pins (PA0-PA7) and
Port B's (PB0-PB7) are fully interactive: clicking a toggle flips that pin's
local-pull state and clicking-and-holding a momentary button asserts the
opposite level for the duration of the press (see `PortIO`/`Peripheral`).
The chevron's fill continues to track live pin-level events from the VIA;
direction stays a declared, panel-side setting (`--pa-direction`/
`--pb-direction`) since the protocol never conveys DDR. CA1/CA2/CB1/CB2 are
momentary-only control lines: level mode drives the active edge for as long
as the button is held, pulse mode fires one fixed-duration transition per
press regardless of hold time, and polarity picks which edge (rising/
falling) counts as "active" (see `ControlPinState`).

PB6 layers T2 pulse-counting behavior on top of an ordinary data pin when
`--pb6-pulse-counting` is declared (default on): it's forced pulled up, and
its toggle is repurposed into the same pulse/level mode-select CA1/CA2 use
for their momentary, since the wire protocol never reports ACR either (see
`PB6State`).

PB7 keeps its ordinary toggle/momentary untouched -- when Timer 1 is in
free-run/PB7-toggle mode, the VIA drives this pin directly regardless of
DDRB7, "the same 'pin can diverge from local' story as any output pin"
(design doc), so no special interactivity wiring is needed here. It layers
two independent things instead: a purely informational, declared
`--pb7-free-run` indicator (again, ACR isn't observable live -- see
`PB6State`) and a panel-local audio-routing toggle plus a naive square-wave
audio reconstruction of PB7's live wire level (see `PB7State`, `Pb7Audio`).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import pygame

from emma65_via import PortBitsReset, PortBitsSet, PortState, ViaAsciiClient

from . import cells

try:
    import sounddevice as sd
except OSError:
    # sounddevice imports fine as a Python package but probes for the
    # PortAudio native library at import time -- raises OSError immediately
    # if it's not installed (e.g. a headless dev/CI box with no audio
    # backend at all). Degrade to silent playback rather than crashing the
    # whole panel over a missing speaker.
    sd = None

DEFAULT_SOCKET = "~/.emma/sock/via6522"
DEFAULT_PA_DIRECTION = 0xF0
DEFAULT_PB_DIRECTION = 0xB8
RECONNECT_INTERVAL_MS = 1000
CTRL_PULSE_DURATION_MS = 100
PB7_AUDIO_SAMPLE_RATE = 44100
PB7_AUDIO_AMPLITUDE = 0.2

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
        help="Declared DDRB value for Port B data pins, as a hex byte -- bit n set means PBn "
        f"is an output (default: {DEFAULT_PB_DIRECTION:02X}, i.e. PB7 out, PB6 in, PB5-PB3 "
        "out, PB2-PB0 in). Same DDR caveat as --pa-direction applies; for PB6/PB7 this is "
        "independent of --pb6-pulse-counting/--pb7-free-run, which govern local pull/audio, "
        "not direction.",
    )
    parser.add_argument(
        "--pb6-pulse-counting", action=argparse.BooleanOptionalAction, default=True,
        help="Declare whether PB6 is wired to Timer 2's external pulse-counting input for "
        "this panel (default: enabled). The VIA peer protocol never reports ACR, so this "
        "can't be read live from the VIA -- same reasoning as --pa-direction/--pb-direction. "
        "When enabled, PB6 is forced pulled up and its toggle is repurposed into a "
        "pulse/level mode-select for the momentary switch; when disabled (--no-pb6-pulse-"
        "counting), PB6 behaves exactly like any other Port B data pin.",
    )
    parser.add_argument(
        "--pb7-free-run", action=argparse.BooleanOptionalAction, default=False,
        help="Declare whether Timer 1 is configured for this panel's ROM/firmware in "
        "free-run/PB7-toggle mode (ACR bits 7:6 = 1x), which drives PB7 automatically to "
        "produce a square wave (default: disabled). The VIA peer protocol never reports "
        "ACR, so this can't be read live -- same reasoning as --pb6-pulse-counting. This "
        "only controls a small informational badge on PB7's cell; it doesn't change PB7's "
        "interactivity (its toggle/momentary work exactly like any other data pin, same as "
        "any output pin that can be driven by both the panel and the VIA).",
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
class PB6State:
    """PB6's declared T2 pulse-counting configuration and momentary mode.

    `pulse_counting` is a declared, CLI-level fact (`--pb6-pulse-counting`)
    -- the VIA peer protocol never reports ACR (same reasoning as the DDR
    finding behind `--pa-direction`/`--pb-direction`), so whether PB6 is
    actually wired to T2's external pulse-counting input can't be read
    live. `mode`/`pulse_release_at` mirror `ControlPinState`'s pulse-vs-
    level timing, applied to PB6's momentary button (`press_pb6`/
    `release_pb6`) instead of a control pin.
    """

    pulse_counting: bool
    mode: cells.Mode = "level"
    pulse_release_at: int | None = None


@dataclass
class PB7State:
    """PB7's declared T1 free-run configuration and panel-local audio routing.

    `free_run` is a declared, CLI-level fact (`--pb7-free-run`) for the same
    reason `PB6State.pulse_counting` is -- the VIA peer protocol never
    reports ACR, so whether T1 is actually driving PB7 automatically can't
    be read live. Unlike PB6, nothing about PB7's own toggle/momentary
    interactivity changes based on this -- it's purely an informational
    badge (`PB7Cell`).

    `speaker_on` is panel-local audio-routing state -- never sent over the
    wire, toggled only by clicking the panel's own speaker icon.
    """

    free_run: bool
    speaker_on: bool = True


@dataclass
class PortIO:
    """Local write-state for one port's data bits and two control pins.

    `num_bits` is how many data lines this panel owns on this port (8 for
    both ports now that Port B's PB7 is in scope) -- it bounds reconnect
    re-assertion so the panel never sends a bit it doesn't own.

    `local` is the toggle position bitmask (bit set = pulling high) -- the
    LED and toggle widgets reflect this directly, except for Port B's bit
    6 when `pb6.pulse_counting` is declared, where it's a fixed fact set
    once at construction rather than something a toggle click flips (see
    `PB6State`). `momentary` is which bits currently have their momentary
    button held, which asserts the *opposite* of the toggle's level for
    the duration of the press (mirroring
    `emma65_buttons.ButtonPeripheral.toggle`/`_send_bit`, generalized from
    one hardcoded bit to 8 independent ones, and now to more than one
    port). `level` is the live pin level read back from the VIA -- this is
    also what `Pb7Audio` reconstructs PB7's audio from, since it's the
    actual node level regardless of which side is driving it. `ctrl` maps
    control-pin number (1 or 2) to its `ControlPinState`. `pb6`/`pb7` are
    only set on Port B.
    """

    num_bits: int = 8
    level: int = 0
    local: int = 0
    momentary: int = 0
    ctrl: dict[int, ControlPinState] = field(default_factory=lambda: {1: ControlPinState(), 2: ControlPinState()})
    pb6: PB6State | None = None
    pb7: PB7State | None = None

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
        port_b = PortIO(
            num_bits=8,
            pb6=PB6State(pulse_counting=args.pb6_pulse_counting),
            pb7=PB7State(free_run=args.pb7_free_run),
        )
        if port_b.pb6.pulse_counting:
            port_b.local |= 1 << 6  # forced pulled up, per PB6State
        self.ports: dict[str, PortIO] = {"A": PortIO(num_bits=8), "B": port_b}
        self.pb7_audio = Pb7Audio(port_b)

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
        """Reverts any control pin, or PB6's declared pulse-counting momentary
        (see `press_pb6`), whose fixed-duration pulse has elapsed back to idle."""
        for port, io in self.ports.items():
            for pin, state in io.ctrl.items():
                if state.pulse_release_at is not None and now_ms >= state.pulse_release_at:
                    state.pulse_release_at = None
                    self._send_ctrl(port, pin, state.idle_level())
            pb6 = io.pb6
            if pb6 is not None and pb6.pulse_release_at is not None and now_ms >= pb6.pulse_release_at:
                pb6.pulse_release_at = None
                io.momentary &= ~(1 << 6)
                self._send_bit(port, 6, io.driven_level(6))

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

    def toggle_pb6_mode(self, port: str) -> None:
        """Flips PB6's repurposed toggle between pulse and level mode (declared pulse-counting only).

        Mirrors `toggle_ctrl_mode`: cancels any in-flight pulse and
        reasserts the idle (pulled-up) level.
        """
        io = self.ports[port]
        pb6 = io.pb6
        pb6.mode = "level" if pb6.mode == "pulse" else "pulse"
        if pb6.pulse_release_at is not None:
            pb6.pulse_release_at = None
            io.momentary &= ~(1 << 6)
            self._send_bit(port, 6, io.driven_level(6))

    def press_pb6(self, port: str, now_ms: int) -> None:
        """Presses PB6's momentary button (declared pulse-counting only).

        Level mode drives the pulled-low level for as long as the button
        stays held, mirroring an ordinary data-bit momentary. Pulse mode
        fires one fixed-duration low pulse regardless of hold time,
        mirroring `press_ctrl` -- suited to driving T2's negative-edge
        pulse-counting input without depending on human timing.
        """
        io = self.ports[port]
        pb6 = io.pb6
        mask = 1 << 6
        io.momentary |= mask
        if pb6.mode == "pulse":
            pb6.pulse_release_at = now_ms + CTRL_PULSE_DURATION_MS
        self._send_bit(port, 6, io.driven_level(6))

    def release_pb6(self, port: str) -> None:
        """Releases PB6's momentary button (declared pulse-counting only).

        Level mode returns to idle (pulled-up) immediately. In pulse mode
        the revert is already scheduled via `update_ctrl_pulses`, so an
        early release doesn't change the wire -- mirrors `release_ctrl`.
        """
        io = self.ports[port]
        pb6 = io.pb6
        if pb6.mode == "level":
            io.momentary &= ~(1 << 6)
            self._send_bit(port, 6, io.driven_level(6))

    def toggle_pb7_speaker(self, port: str) -> None:
        """Flips PB7's panel-local audio-routing state -- never touches the wire.

        Purely a local setting `Pb7Audio` reads each callback; there's no
        VIA-side concept of "audio routing" to send.
        """
        io = self.ports[port]
        io.pb7.speaker_on = not io.pb7.speaker_on

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
        self.pb7_audio.close()


class Pb7Audio:
    """Reconstructs PB7's live wire level as a naive, non-band-limited square wave.

    Per the design doc's "Audio output" section, this peripheral is
    external to the emulator, so reconstruction is driven entirely by the
    Set/Reset message stream for PB7 -- not in-process timing -- and reads
    whatever `port_b.level`'s bit 7 currently is: the actual node level,
    whichever side is driving it. No synthesis math is needed since the
    signal is already a literal square wave; each output sample is just
    +/-`PB7_AUDIO_AMPLITUDE` depending on that bit, muted to 0 whenever
    `port_b.pb7.speaker_on` is off.

    The audio callback runs on PortAudio's own thread, reading `port_b`'s
    plain int/bool attributes that the pygame-thread main loop mutates
    without a lock -- safe here only because CPython's GIL makes a single
    attribute read/write atomic and there's no multi-step invariant being
    read across two attributes at once (bit 7 of `level` and `speaker_on`
    are each read independently, and either one glitching by at most one
    sample block is inaudible). This is the first cross-thread state in
    the whole codebase; don't assume this pattern generalizes to a future
    case with a real invariant to protect.

    Gracefully does nothing if `sounddevice`/PortAudio isn't usable in this
    environment (no import, no audio device, construction/start failure)
    -- audio is a nice-to-have on top of the panel, not a requirement to
    run it, mirroring how the rest of the panel degrades (e.g. reconnect
    backoff) rather than crashing on an unavailable resource.
    """

    def __init__(self, port_b: PortIO):
        self._port_b = port_b
        self._stream = None
        if sd is None:
            return
        try:
            stream = sd.OutputStream(
                samplerate=PB7_AUDIO_SAMPLE_RATE, channels=1, dtype="float32", callback=self._callback,
            )
            stream.start()
        except Exception:
            return
        self._stream = stream

    def _callback(self, outdata, frames, time_info, status) -> None:
        pb7 = self._port_b.pb7
        if pb7 is not None and pb7.speaker_on and (self._port_b.level & 0x80):
            outdata[:, 0] = PB7_AUDIO_AMPLITUDE
        elif pb7 is not None and pb7.speaker_on:
            outdata[:, 0] = -PB7_AUDIO_AMPLITUDE
        else:
            outdata[:, 0] = 0.0

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


def run(args: argparse.Namespace) -> None:
    pygame.init()
    pygame.display.set_caption("emma65 VIA GPIO playground")

    ports = [
        cells.build_port_a(args.pa_direction),
        cells.build_port_b(args.pb_direction, args.pb6_pulse_counting, args.pb7_free_run),
    ]
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
    pressed_momentary: cells.DataCell | None = None
    pressed_ctrl: tuple[str, int] | None = None

    def is_pb6_pulse_counting(cell: cells.DataCell) -> bool:
        return isinstance(cell, cells.PB6Cell) and cell.pulse_counting

    running = True
    while running:
        now_ms = pygame.time.get_ticks()
        peripheral.connect_if_needed(now_ms)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for cell in data_cells:
                    if isinstance(cell, cells.PB7Cell) and cell.speaker_rect().collidepoint(event.pos):
                        peripheral.toggle_pb7_speaker(cell.port)
                        break
                    if cell.toggle_rect().collidepoint(event.pos):
                        if is_pb6_pulse_counting(cell):
                            peripheral.toggle_pb6_mode(cell.port)
                        else:
                            peripheral.toggle_data(cell.port, cell.bit)
                        break
                    if cell.momentary_rect().collidepoint(event.pos):
                        if is_pb6_pulse_counting(cell):
                            peripheral.press_pb6(cell.port, now_ms)
                        else:
                            peripheral.set_momentary(cell.port, cell.bit, True)
                        pressed_momentary = cell
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
                    if is_pb6_pulse_counting(pressed_momentary):
                        peripheral.release_pb6(pressed_momentary.port)
                    else:
                        peripheral.set_momentary(pressed_momentary.port, pressed_momentary.bit, False)
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
            if is_pb6_pulse_counting(cell):
                cell.mode = io.pb6.mode
            if isinstance(cell, cells.PB7Cell):
                cell.speaker_on = io.pb7.speaker_on
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
