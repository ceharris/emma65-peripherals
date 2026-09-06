"""Reusable pin-cell rendering: the Cell / DataCell / ControlCell hierarchy.

Translates the settled visual language from the GPIO playground design
checkpoints (`gpio-playground/plan/via_gpio_playground_ui_checkpoint.md`,
`..._checkpoint_2.md`, reference mockup `row_mockup.py`) into structured,
reusable widget classes. Cells only carry rendering state and hit-test
geometry; live VIA data and interactivity are owned by `Peripheral` in
`app.py` and pushed into cells each frame.

Row layout (`layout_row`) is a function of a list of `Cell`s and a starting
x-position, not hardcoded to one port, so Port B (Unit 7) becomes a second
call into this same code instead of a duplicated block that can drift out
of sync (the risk checkpoint 2 flagged explicitly). `build_port` is the
single pin-list constructor behind both `build_port_a`/`build_port_b`, and
`layout_ports` composes multiple `layout_row` calls (one per port,
separated by `PORT_GAP`) so a combined multi-port canvas is measured and
placed the same drift-proof way checkpoint 2 established for one row.

`PB6Cell` (Unit 8) is a thin `DataCell` decorator for PB6's layered T2
pulse-counting capability -- see its own docstring. `PB7Cell` (Unit 9) is
the analogous decorator for PB7's T1 free-run informational indicator and
audio-routing (speaker) control.
"""

from __future__ import annotations

from typing import Literal

import pygame

Direction = Literal["in", "out"]
Mode = Literal["pulse", "level"]
Polarity = Literal["rising", "falling"]

# ---- Palette ----
BG = (22, 24, 28)
PANEL = (32, 35, 40)
PANEL_EDGE = (52, 56, 62)
TEXT = (215, 218, 222)
TEXT_DIM = (140, 145, 152)
LED_HIGH = (86, 214, 128)
LED_LOW = (60, 64, 70)
DIR_IN = (86, 156, 232)
DIR_OUT = (214, 122, 86)
TOGGLE_ON = (86, 214, 128)
TOGGLE_OFF = (58, 62, 68)
BTN = (70, 75, 82)
BTN_EDGE = (98, 104, 112)
ACCENT = (244, 196, 92)

# PB7's audio-routing (speaker) icon -- a dedicated hue per checkpoint 2,
# since LED green, direction blue/orange, and accent gold are all already
# carrying other meanings.
SPKR_ON = (176, 141, 235)

# Glow-ring outer radius, as a multiple of the lit LED/momentary-button's own
# radius -- shared by draw_led and draw_momentary per checkpoint 2's decision
# to reuse the LED's glow styling for the momentary button.
GLOW_RADIUS_SCALE = 1.3

# "15-segment" mode display -- stylized stand-in, not real per-glyph segment
# geometry (see checkpoint 2). Dark backlit rect + bold monospace text in an
# LED/VFD-style amber.
SEG_BG = (12, 12, 14)
SEG_ON = (255, 153, 51)

# ---- Global scale ----
# Layout constants below are tuned at a base fidelity for a ~468px-wide
# single-port row, then multiplied by S (checkpoint 2's "scale the whole
# mockup" fix) so retuning fidelity is a single-number change.
S = 600 / 468


def sc(v: float) -> int:
    return round(v * S)


# ---- Row layout constants ----
chevron_size = sc(28)  # matches LED diameter
label_center_y = sc(66)  # PAx / CAx label, floats above everything
chevron_y0 = label_center_y + sc(12)
row_y = chevron_y0 + chevron_size + sc(10)  # cell top, below the chevron
cell_h = sc(200)  # keyed to the control cells' toggle+display+polarity stack
ctrl_w = sc(40)  # equalized to data_w per checkpoint 2 (spacing is now the
data_w = sc(40)  # only cue distinguishing control cells from data cells)
gap = sc(6)
ctrl_group_gap = sc(14)  # extra space before the first control cell
PORT_GAP = sc(28)  # extra space between two ports' cell groups -- wider than
                    # ctrl_group_gap so multiple ports read as separate panels
LEFT_MARGIN = sc(20)  # mirrored on the right for symmetric canvas margins

status_h = sc(40)
CONTENT_HEIGHT = row_y + cell_h

# per-cell vertical offsets (from rect.top), shared across the row so that
# widgets of the same kind line up regardless of which cell they're in
LED_OFF_DATA = sc(30)
LED_OFF_CTRL = sc(26)
TOGGLE_OFF = sc(76)
SEG_OFF = sc(104)
POLARITY_OFF = sc(135)
MOMENTARY_OFF = sc(170)


def draw_text(surf, font, text, color, center=None, topleft=None):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = center
    if topleft:
        rect.topleft = topleft
    surf.blit(img, rect)
    return rect


def draw_led(surf, cx, cy, r, on):
    color = LED_HIGH if on else LED_LOW
    if on:
        glow_r = int(r * GLOW_RADIUS_SCALE)
        glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*color, 70), (glow_r, glow_r), glow_r)
        surf.blit(glow, (cx - glow_r, cy - glow_r))
    pygame.draw.circle(surf, color, (cx, cy), r)
    pygame.draw.circle(surf, (0, 0, 0, 255), (cx, cy), r, 1)


def draw_toggle(surf, cx, cy, w, h, on):
    rect = pygame.Rect(0, 0, w, h)
    rect.center = (cx, cy)
    pygame.draw.rect(surf, TOGGLE_ON if on else TOGGLE_OFF, rect, border_radius=h // 2)
    knob_x = rect.right - h // 2 if on else rect.left + h // 2
    pygame.draw.circle(surf, (240, 240, 240), (knob_x, cy), h // 2 - 2)


def draw_momentary(surf, cx, cy, r, pressed=False):
    body = ACCENT if pressed else BTN
    edge = ACCENT if pressed else BTN_EDGE
    if pressed:
        glow_r = int(r * GLOW_RADIUS_SCALE)
        glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*ACCENT, 70), (glow_r, glow_r), glow_r)
        surf.blit(glow, (cx - glow_r, cy - glow_r))
    pygame.draw.circle(surf, body, (cx, cy), r)
    pygame.draw.circle(surf, edge, (cx, cy), r, 2)
    pygame.draw.circle(surf, (0, 0, 0), (cx, cy), max(1, r - 6), 1)


def draw_chevron(surf, cx, y0, size, direction: Direction, filled: bool):
    # direction: 'in' (apex up) | 'out' (apex down). Filled = pin state
    # high, outline = pin state low -- the actual node level the VIA sees.
    color = DIR_IN if direction == "in" else DIR_OUT
    half = size / 2
    if direction == "in":
        points = [(cx - half, y0 + size), (cx + half, y0 + size), (cx, y0)]
    else:
        points = [(cx - half, y0), (cx + half, y0), (cx, y0 + size)]
    if filled:
        pygame.draw.polygon(surf, color, points)
    else:
        pygame.draw.polygon(surf, color, points, width=2)


def draw_seg_display(surf, font, cx, cy, text, color=SEG_ON):
    # Auto-sized to the text plus a tight pad, rather than a fixed box.
    pad_x, pad_y = sc(3), sc(2)
    text_w, text_h = font.size(text)
    w, h = text_w + pad_x * 2, text_h + pad_y * 2
    rect = pygame.Rect(0, 0, w, h)
    rect.center = (cx, cy)
    pygame.draw.rect(surf, SEG_BG, rect, border_radius=3)
    pygame.draw.rect(surf, PANEL_EDGE, rect, width=1, border_radius=3)
    draw_text(surf, font, text, color, center=rect.center)


def draw_pulse_icon(surf, cx, cy, w, h, polarity: Polarity):
    # Polarity doubles as pull direction: "rising" = pulled down (idle low,
    # brief high pulse), "falling" = pulled up (idle high, brief low
    # pulse). The active edge is bold/colored; the return-to-idle edge
    # stays dim.
    active = DIR_IN if polarity == "rising" else DIR_OUT
    bottom_y, top_y = cy + h / 2, cy - h / 2
    x0 = cx - w / 2
    x1 = x0 + w * 0.32
    x2 = x0 + w * 0.68
    x3 = cx + w / 2
    if polarity == "rising":
        idle_y, excursion_y = bottom_y, top_y
    else:
        idle_y, excursion_y = top_y, bottom_y
    pygame.draw.line(surf, TEXT_DIM, (x0, idle_y), (x1, idle_y), 1)
    pygame.draw.line(surf, active, (x1, idle_y), (x1, excursion_y), 3)
    pygame.draw.line(surf, TEXT_DIM, (x1, excursion_y), (x2, excursion_y), 1)
    pygame.draw.line(surf, TEXT_DIM, (x2, excursion_y), (x2, idle_y), 1)
    pygame.draw.line(surf, TEXT_DIM, (x2, idle_y), (x3, idle_y), 1)


def draw_speaker_icon(surf, cx, cy, on: bool, scale: float = 1.0) -> None:
    # Modeled directly on a standard speaker glyph: a narrow box flaring
    # into a wide cone, with wave arcs off the apex when routing is on. No
    # background badge -- same "bare shape" treatment as the chevron and
    # polarity icon (checkpoint 2's second design pass; a circular
    # icon-button first attempt didn't read as a speaker at cell scale).
    #
    # The box+cone silhouette alone is horizontally symmetric, but the wave
    # arcs only extend rightward from the apex -- so centering the box+cone
    # at cx left the whole glyph, arcs included, visibly off-center when
    # routing was on. Instead, the full bounding box for the current state
    # (arcs included, when present) is centered at cx, so the box+cone
    # shifts left to make room for the arcs on the right.
    color = SPKR_ON if on else TEXT_DIM
    box_w, cone_len = 7 * scale, 8 * scale
    box_h, apex_h = 6 * scale, 13 * scale
    arc_radii = (6 * scale, 11 * scale)

    box_cone_w = box_w + cone_len
    total_w = box_cone_w + (arc_radii[-1] if on else 0)
    x0 = cx - total_w / 2
    apex_x = x0 + box_cone_w

    poly = [
        (x0, cy - box_h), (x0 + box_w, cy - box_h),
        (apex_x, cy - apex_h), (apex_x, cy + apex_h),
        (x0 + box_w, cy + box_h), (x0, cy + box_h),
    ]
    pygame.draw.polygon(surf, color, poly)

    if on:
        for rad in arc_radii:
            arc_rect = pygame.Rect(0, 0, rad * 2, rad * 2)
            arc_rect.center = (apex_x, cy)
            pygame.draw.arc(surf, color, arc_rect, -1.0, 1.0, max(2, int(3 * scale)))
    else:
        # Muted: a single diagonal stroke across the whole glyph, in a
        # brighter contrasting color (TEXT, not TEXT_DIM) than the dimmed
        # fill -- checkpoint 2 caught a first attempt that used the same
        # dim color as the fill, which only read as a stray floating mark
        # where it extended past the icon's own silhouette rather than a
        # slash through it. Worth remembering for any icon with an on/off
        # pair: render both states before calling either one settled.
        lw = max(2, int(3 * scale))
        pygame.draw.line(surf, TEXT, (x0, cy - apex_h), (apex_x, cy + apex_h), lw)


UI_FONT = "Arial,Helvetica,DejaVu Sans,sans-serif"


class Fonts:
    """Fonts used by cell rendering. Created after `pygame.font.init()`.

    `label` and `seg` stay monospace -- pin labels (PA7, ...) want the
    fixed-width alignment across the row, and the segment display is
    intentionally styled as a digital/VFD readout (checkpoint 2). Status
    bar and connection-status chrome use a regular UI font instead: their
    monospace rendering was just inherited from the mockup reusing one
    font everywhere, not a deliberate design choice, and reads as
    unpolished for plain prose text like "OVERLOAD" or "MODE: FREE".
    """

    def __init__(self):
        self.label = pygame.font.SysFont("Consolas,Menlo,monospace", sc(16), bold=True)
        self.seg = pygame.font.SysFont("Consolas,Menlo,monospace", sc(13), bold=True)
        self.ui_title = pygame.font.SysFont(UI_FONT, sc(16), bold=True)
        self.ui_small = pygame.font.SysFont(UI_FONT, sc(12))


class Cell:
    """Base for one pin's vertical module: label, chevron, cell body.

    Generic in structure regardless of which physical pin it represents --
    the label+chevron pair above the body is what specializes an otherwise
    interchangeable cell to a given pin (checkpoint 1).
    """

    kind: str

    def __init__(self, name: str, direction: Direction, port: str = ""):
        self.name = name
        self.direction = direction
        self.port = port
        self.rect = pygame.Rect(0, 0, 0, 0)

    @property
    def width(self) -> int:
        raise NotImplementedError

    def place(self, x: int) -> int:
        """Positions this cell's rect with its left edge at x. Returns the x for the next cell."""
        self.rect = pygame.Rect(x, row_y, self.width, cell_h)
        return x + self.width + gap

    def _chevron_filled(self) -> bool:
        raise NotImplementedError

    def _draw_body(self, surf, fonts: Fonts) -> None:
        raise NotImplementedError

    def draw(self, surf, fonts: Fonts) -> None:
        draw_text(surf, fonts.label, self.name, TEXT, center=(self.rect.centerx, label_center_y))
        draw_chevron(surf, self.rect.centerx, chevron_y0, chevron_size, self.direction, self._chevron_filled())
        pygame.draw.rect(surf, PANEL, self.rect, border_radius=10)
        pygame.draw.rect(surf, PANEL_EDGE, self.rect, width=1, border_radius=10)
        self._draw_body(surf, fonts)


class DataCell(Cell):
    """A data pin (PAx/PBx): LED (driven output), toggle (local pull), momentary button.

    The toggle reflects `local` -- the level the panel's own toggle pulls
    the pin toward. The LED reflects `driven` -- what the panel is actually
    asserting onto the pin right now, which is `local` unless a held
    momentary button is overriding it to the opposite level (so pressing
    momentary on a pulled-up pin dims the LED, and on a pulled-down pin
    lights it -- the LED must visibly move the instant the momentary is
    pressed, not just show toggle position). `pin` is the actual node level
    the VIA sees, shown by the chevron; it can diverge from `driven` on an
    output pin (pull-up/down losing to an active VIA driver, or contention).
    """

    kind = "data"

    def __init__(
        self,
        name: str,
        direction: Direction,
        local: bool,
        pin: bool,
        momentary_pressed: bool = False,
        bit: int | None = None,
        port: str = "",
    ):
        super().__init__(name, direction, port=port)
        self.local = local
        self.pin = pin
        self.momentary_pressed = momentary_pressed
        self.bit = bit

    @property
    def width(self) -> int:
        return data_w

    @property
    def driven(self) -> bool:
        """The level this cell is actually asserting onto the pin right now:
        `local`, unless a held momentary button is overriding it to the
        opposite level for its duration."""
        return self.local != self.momentary_pressed

    def _chevron_filled(self) -> bool:
        return self.pin

    def toggle_rect(self) -> pygame.Rect:
        """Clickable area for this cell's toggle switch, for hit-testing."""
        rect = pygame.Rect(0, 0, sc(28), sc(15))
        rect.center = (self.rect.centerx, self.rect.top + TOGGLE_OFF)
        return rect

    def momentary_rect(self) -> pygame.Rect:
        """Clickable area for this cell's momentary button, for hit-testing."""
        r = sc(12)
        rect = pygame.Rect(0, 0, r * 2, r * 2)
        rect.center = (self.rect.centerx, self.rect.top + MOMENTARY_OFF)
        return rect

    def _draw_body(self, surf, fonts: Fonts) -> None:
        draw_led(surf, self.rect.centerx, self.rect.top + LED_OFF_DATA, sc(13), on=self.driven)
        toggle_rect = self.toggle_rect()
        draw_toggle(surf, *toggle_rect.center, toggle_rect.width, toggle_rect.height, on=self.local)
        momentary_rect = self.momentary_rect()
        draw_momentary(surf, *momentary_rect.center, momentary_rect.width // 2, pressed=self.momentary_pressed)


class PB6Cell(DataCell):
    """PB6: full standard data-cell anatomy plus a layered T2 pulse-counting capability.

    Per the design doc, PB6 "behaves like any other data pin except when
    T2's pulse-counting mode is active" -- a layered capability, not a
    replacement. Whether that layered behavior applies to this panel is a
    declared, CLI-level setting (`pulse_counting`), not something read
    live: the VIA peer protocol never reports ACR (see
    `emma65_via.protocol`'s module docstring), the same reasoning that
    made pin direction a declared setting rather than a DDR readback
    (Unit 4).

    When `pulse_counting` is True:
    - `local` is forced True (pulled up, required for pulse counting) at
      construction and never flipped by a toggle click again.
    - The ordinary local-pull toggle is repurposed into a pulse/level
      mode-select (`mode`) for the momentary switch, reusing the same
      toggle position and the segment-display real estate `ControlCell`
      uses one gap below it.
    - The LED still shows `driven` (local XOR momentary, same formula as
      any `DataCell`), even though `local` no longer reflects a user's
      toggle position moment to moment -- an ambiguity checkpoint 2 flagged
      that's left unresolved for now (see the design doc).

    When `pulse_counting` is False, PB6 draws and behaves exactly like any
    other `DataCell`.
    """

    def __init__(
        self,
        name: str,
        direction: Direction,
        local: bool,
        pin: bool,
        pulse_counting: bool,
        mode: Mode = "level",
        momentary_pressed: bool = False,
        bit: int | None = None,
        port: str = "",
    ):
        super().__init__(name, direction, local, pin, momentary_pressed, bit, port)
        self.pulse_counting = pulse_counting
        self.mode = mode

    def _draw_body(self, surf, fonts: Fonts) -> None:
        if not self.pulse_counting:
            super()._draw_body(surf, fonts)
            return
        led_cy = self.rect.top + LED_OFF_DATA
        draw_led(surf, self.rect.centerx, led_cy, sc(13), on=self.driven)
        toggle_rect = self.toggle_rect()
        draw_toggle(surf, *toggle_rect.center, toggle_rect.width, toggle_rect.height, on=(self.mode == "pulse"))
        seg_text = "PLS" if self.mode == "pulse" else "LVL"
        draw_seg_display(surf, fonts.seg, self.rect.centerx, self.rect.top + SEG_OFF, seg_text)
        momentary_rect = self.momentary_rect()
        draw_momentary(surf, *momentary_rect.center, momentary_rect.width // 2, pressed=self.momentary_pressed)


class PB7Cell(DataCell):
    """PB7: full standard data-cell anatomy plus a T1 free-run indicator and a speaker icon.

    Unlike PB6, PB7's toggle and momentary are never repurposed -- the
    design doc is explicit that T1 driving PB7 is "the same 'pin can
    diverge from local' story as any output pin," so this cell's ordinary
    `DataCell` toggle/momentary interactivity is left untouched. Two extra,
    independent widgets fill the gaps an ordinary `DataCell` leaves empty
    between its toggle and momentary:

    - `free_run` (declared, immutable after construction, same reasoning
      as `PB6Cell.pulse_counting`): the VIA peer protocol never reports ACR
      (see `emma65_via.protocol`'s module docstring and the Unit 8 PB6
      precedent), so whether Timer 1 is actually in free-run/PB7-toggle
      mode can't be read live -- there is also no wire-traffic signature
      reliable enough to infer it (a human clicking the panel's own
      momentary can produce similar-looking Set/Reset bursts). This is
      shown as a small amber segment-display badge reading "T1", bright
      when declared and dim otherwise -- reusing the same widget position
      and visual language `PB6Cell`/`ControlCell` use for their own
      mode-select displays, per checkpoint 2's request to converge on one
      shared "special-case cell carries an extra gap-filling widget"
      pattern rather than a third bespoke one. Unlike those, this badge is
      purely informational (its text never changes; only its brightness
      does) since there's nothing here for a click to toggle.
    - `speaker_on` (panel-local, mutable via a click on the icon; never
      sent over the wire): whether this panel's own audio-reconstruction
      output is currently routed to the speaker. Rendered with
      `draw_speaker_icon` at the same offset `ControlCell`'s polarity icon
      uses, matching checkpoint 2's alignment of the row's single-item
      gap-fillers.
    """

    def __init__(
        self,
        name: str,
        direction: Direction,
        local: bool,
        pin: bool,
        free_run: bool,
        speaker_on: bool = True,
        momentary_pressed: bool = False,
        bit: int | None = None,
        port: str = "",
    ):
        super().__init__(name, direction, local, pin, momentary_pressed, bit, port)
        self.free_run = free_run
        self.speaker_on = speaker_on

    def speaker_rect(self) -> pygame.Rect:
        """Clickable area for the audio-routing speaker icon, for hit-testing."""
        rect = pygame.Rect(0, 0, sc(30), sc(26))
        rect.center = (self.rect.centerx, self.rect.top + POLARITY_OFF)
        return rect

    def _draw_body(self, surf, fonts: Fonts) -> None:
        super()._draw_body(surf, fonts)
        badge_color = SEG_ON if self.free_run else TEXT_DIM
        draw_seg_display(surf, fonts.seg, self.rect.centerx, self.rect.top + SEG_OFF, "T1", color=badge_color)
        speaker_rect = self.speaker_rect()
        draw_speaker_icon(surf, *speaker_rect.center, on=self.speaker_on, scale=S)


class ControlCell(Cell):
    """A control pin (CAx/CBx): mode toggle + PLS/LVL readout, polarity icon, momentary.

    The chevron is intentionally always outlined -- control-line direction
    is context-dependent on live PCR state, which isn't derived yet
    (checkpoint 1's documented placeholder). The LED stays dark: per
    checkpoint 2 it should show the pin's level only when this line is
    currently serving as a VIA-driven output, which isn't wired up yet.
    """

    kind = "ctrl"

    def __init__(
        self,
        name: str,
        direction: Direction,
        mode: Mode,
        polarity: Polarity,
        momentary_pressed: bool = False,
        ctrl_pin: int | None = None,
        port: str = "",
    ):
        super().__init__(name, direction, port=port)
        self.mode = mode
        self.polarity = polarity
        self.momentary_pressed = momentary_pressed
        self.ctrl_pin = ctrl_pin

    @property
    def width(self) -> int:
        return ctrl_w

    def _chevron_filled(self) -> bool:
        return False

    def mode_rect(self) -> pygame.Rect:
        """Clickable area for the pulse/level mode toggle, for hit-testing."""
        rect = pygame.Rect(0, 0, sc(28), sc(15))
        rect.center = (self.rect.centerx, self.rect.top + TOGGLE_OFF)
        return rect

    def polarity_rect(self) -> pygame.Rect:
        """Clickable area for the polarity pulse-graph icon, for hit-testing."""
        rect = pygame.Rect(0, 0, sc(30), sc(16))
        rect.center = (self.rect.centerx, self.rect.top + POLARITY_OFF)
        return rect

    def momentary_rect(self) -> pygame.Rect:
        """Clickable area for this cell's momentary button, for hit-testing."""
        r = sc(13)
        rect = pygame.Rect(0, 0, r * 2, r * 2)
        rect.center = (self.rect.centerx, self.rect.top + MOMENTARY_OFF)
        return rect

    def _draw_body(self, surf, fonts: Fonts) -> None:
        draw_led(surf, self.rect.centerx, self.rect.top + LED_OFF_CTRL, sc(12), on=False)
        toggle_rect = self.mode_rect()
        draw_toggle(surf, *toggle_rect.center, toggle_rect.width, toggle_rect.height, on=(self.mode == "pulse"))
        seg_text = "PLS" if self.mode == "pulse" else "LVL"
        draw_seg_display(surf, fonts.seg, self.rect.centerx, self.rect.top + SEG_OFF, seg_text)
        polarity_rect = self.polarity_rect()
        draw_pulse_icon(surf, *polarity_rect.center, polarity_rect.width, polarity_rect.height, self.polarity)
        momentary_rect = self.momentary_rect()
        draw_momentary(surf, *momentary_rect.center, momentary_rect.width // 2, pressed=self.momentary_pressed)


def layout_row(cells: list[Cell], start_x: int) -> int:
    """Positions `cells` left-to-right starting at start_x. Returns the row's right edge.

    Single source of truth for cell positions, used both to measure a
    row's content width (so a canvas can be sized with equal margins) and
    to actually place cells for drawing -- so the two can't drift apart
    (checkpoint 2's fix for the mockup's margin/ordering bug).
    """
    x = start_x
    prev_kind = None
    for cell in cells:
        if prev_kind == "data" and cell.kind == "ctrl":
            x += ctrl_group_gap
        x = cell.place(x)
        prev_kind = cell.kind
    return x - gap


def layout_ports(ports: list[list[Cell]], start_x: int) -> int:
    """Lays out multiple ports left-to-right via `layout_row`, separated by `PORT_GAP`.

    Single source of truth for a combined multi-port canvas's positions,
    used both to measure total content width (equal margins on a combined
    canvas) and to actually place cells -- mirroring `layout_row`'s own
    measure/place contract for one port, so the two still can't drift apart
    now that there's more than one row sharing a canvas (Unit 7).
    """
    x = start_x
    right = x
    for i, port in enumerate(ports):
        if i > 0:
            x += PORT_GAP
        right = layout_row(port, x)
        x = right + gap
    return right


def build_port(letter: str, num_bits: int, direction_mask: int = 0x00) -> list[Cell]:
    """Generic port row: P<letter><num_bits-1>..P<letter>0, C<letter>1, C<letter>2.

    `direction_mask` bit *n* set means pin *n* is declared an output. This is
    a declared property of how the panel is wired for a given ROM/firmware,
    not something read from the VIA -- the peer protocol never conveys DDR
    (see `emma65_via.protocol`'s module docstring), and on real hardware an
    external peripheral has no way to query it either. A mismatch between
    this declaration and the firmware's actual DDR shows up as chevron/LED
    divergence (and, from Unit 10, the Overload indicator) rather than an
    error -- the panel doesn't enforce correct configuration, mirroring real
    hardware.

    C<letter>1 is always declared "in" and C<letter>2 "out" -- CA1/CB1 are
    always inputs on real 6522 hardware, unlike CA2/CB2 which are
    configurable; "out" is just this panel's demo default for the
    configurable one, not a hardware constraint the way CA1/CB1's "in" is.

    `local` and `pin` both start low; the caller keeps `pin` live from VIA
    port-state events and `local`/`momentary_pressed` live from the panel's
    own toggle/momentary interactivity (see `Peripheral` in `app.py`).
    """
    data_cells = [
        DataCell(
            f"P{letter}{n}",
            direction=("out" if (direction_mask >> n) & 1 else "in"),
            local=False, pin=False, bit=n, port=letter,
        )
        for n in range(num_bits - 1, -1, -1)
    ]
    return data_cells + [
        ControlCell(f"C{letter}1", direction="in", mode="level", polarity="rising", ctrl_pin=1, port=letter),
        ControlCell(f"C{letter}2", direction="out", mode="level", polarity="rising", ctrl_pin=2, port=letter),
    ]


def build_port_a(direction_mask: int = 0xF0) -> list[Cell]:
    """Port A row: PA7..PA0 (direction per `direction_mask`), CA1, CA2.

    See `build_port` for the shared semantics of `direction_mask`.
    """
    return build_port("A", 8, direction_mask)


def build_port_b(
    direction_mask: int = 0xB8, pulse_counting: bool = True, free_run: bool = False,
) -> list[Cell]:
    """Port B row: PB7 (see `PB7Cell`), PB6 (see `PB6Cell`), PB5..PB0
    (direction per `direction_mask`), CB1, CB2.

    PB0-PB5 and the control cells come from the shared `build_port`
    constructor unchanged; PB6 and PB7 are layered on separately since
    their cell types (`PB6Cell`, `PB7Cell`) and declared settings
    (`pulse_counting`, `free_run`) are unique to those two bits. See
    `build_port` for the shared semantics of `direction_mask`, `PB6Cell`
    for `pulse_counting`, and `PB7Cell` for `free_run`.
    """
    port = build_port("B", 6, direction_mask & 0x3F)
    data_cells, ctrl_cells = port[:-2], port[-2:]
    pb6 = PB6Cell(
        "PB6",
        direction=("out" if (direction_mask >> 6) & 1 else "in"),
        local=pulse_counting, pin=False, pulse_counting=pulse_counting,
        bit=6, port="B",
    )
    pb7 = PB7Cell(
        "PB7",
        direction=("out" if (direction_mask >> 7) & 1 else "in"),
        local=False, pin=False, free_run=free_run,
        bit=7, port="B",
    )
    return [pb7, pb6] + data_cells + ctrl_cells


def draw_status_bar(surf, fonts, title: str, width: int) -> None:
    """Status-bar chrome: title, `emma65` wordmark, OVERLOAD/MODE placeholders.

    OVERLOAD and MODE are static placeholders here -- they get wired up in
    Units 10-11 (contention detection, Free/Guarded mode).
    """
    pygame.draw.rect(surf, PANEL, (0, 0, width, status_h))
    pygame.draw.line(surf, PANEL_EDGE, (0, status_h), (width, status_h), 1)
    draw_led(surf, sc(24), sc(20), sc(8), on=False)
    draw_text(surf, fonts.ui_small, "OVERLOAD", TEXT_DIM, topleft=(sc(40), sc(13)))
    draw_text(surf, fonts.ui_small, "MODE: FREE", ACCENT, topleft=(width - sc(160), sc(13)))
    draw_text(surf, fonts.ui_title, title, TEXT, center=(width // 2, sc(20)))
    draw_text(surf, fonts.ui_small, "emma65", TEXT_DIM, topleft=(width - sc(46), sc(13)))
