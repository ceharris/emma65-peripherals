"""Reusable pin-cell rendering: the Cell / DataCell / ControlCell hierarchy.

Translates the settled visual language from the GPIO playground design
checkpoints (`gpio-playground/plan/via_gpio_playground_ui_checkpoint.md`,
`..._checkpoint_2.md`, reference mockup `row_mockup.py`) into structured,
reusable widget classes, all state carried statically for now -- live VIA
data and interactivity land in later units.

Row layout (`layout_row`) is a function of a list of `Cell`s and a starting
x-position, not hardcoded to one port, so Port B (Unit 7) becomes a second
call into this same code instead of a duplicated block that can drift out
of sync (the risk checkpoint 2 flagged explicitly).
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
        glow_r = int(r * 1.6)
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
        glow_r = int(r * 1.6)
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


class Fonts:
    """Fonts used by cell rendering. Created after `pygame.font.init()`."""

    def __init__(self):
        self.label = pygame.font.SysFont("Consolas,Menlo,monospace", sc(16), bold=True)
        self.seg = pygame.font.SysFont("Consolas,Menlo,monospace", sc(13), bold=True)


class Cell:
    """Base for one pin's vertical module: label, chevron, cell body.

    Generic in structure regardless of which physical pin it represents --
    the label+chevron pair above the body is what specializes an otherwise
    interchangeable cell to a given pin (checkpoint 1).
    """

    kind: str

    def __init__(self, name: str, direction: Direction):
        self.name = name
        self.direction = direction
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
    """A data pin (PAx/PBx): LED (local pull), toggle, momentary button.

    LED and toggle both reflect `local` -- the level the panel's own
    toggle pulls the pin toward. `pin` is the actual node level the VIA
    sees, shown by the chevron; it can diverge from `local` on an output
    pin (pull-up/down losing to an active VIA driver, or contention).
    """

    kind = "data"

    def __init__(self, name: str, direction: Direction, local: bool, pin: bool, momentary_pressed: bool = False):
        super().__init__(name, direction)
        self.local = local
        self.pin = pin
        self.momentary_pressed = momentary_pressed

    @property
    def width(self) -> int:
        return data_w

    def _chevron_filled(self) -> bool:
        return self.pin

    def _draw_body(self, surf, fonts: Fonts) -> None:
        draw_led(surf, self.rect.centerx, self.rect.top + LED_OFF_DATA, sc(13), on=self.local)
        draw_toggle(surf, self.rect.centerx, self.rect.top + TOGGLE_OFF, sc(28), sc(15), on=self.local)
        draw_momentary(surf, self.rect.centerx, self.rect.top + MOMENTARY_OFF, sc(12), pressed=self.momentary_pressed)


class ControlCell(Cell):
    """A control pin (CAx/CBx): mode toggle + PUL/LVL readout, polarity icon, momentary.

    The chevron is intentionally always outlined -- control-line direction
    is context-dependent on live PCR state, which isn't derived yet
    (checkpoint 1's documented placeholder). The LED stays dark: per
    checkpoint 2 it should show the pin's level only when this line is
    currently serving as a VIA-driven output, which isn't wired up yet.
    """

    kind = "ctrl"

    def __init__(self, name: str, direction: Direction, mode: Mode, polarity: Polarity):
        super().__init__(name, direction)
        self.mode = mode
        self.polarity = polarity

    @property
    def width(self) -> int:
        return ctrl_w

    def _chevron_filled(self) -> bool:
        return False

    def _draw_body(self, surf, fonts: Fonts) -> None:
        draw_led(surf, self.rect.centerx, self.rect.top + LED_OFF_CTRL, sc(12), on=False)
        draw_toggle(surf, self.rect.centerx, self.rect.top + TOGGLE_OFF, sc(28), sc(15), on=(self.mode == "pulse"))
        seg_text = "PUL" if self.mode == "pulse" else "LVL"
        draw_seg_display(surf, fonts.seg, self.rect.centerx, self.rect.top + SEG_OFF, seg_text)
        draw_pulse_icon(surf, self.rect.centerx, self.rect.top + POLARITY_OFF, sc(30), sc(16), self.polarity)
        draw_momentary(surf, self.rect.centerx, self.rect.top + MOMENTARY_OFF, sc(13), pressed=False)


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


def build_port_a() -> list[Cell]:
    """Port A row with static placeholder state (PA7..PA0, CA1, CA2).

    Values are chosen to exercise the distinct visual cases from the
    design checkpoints -- agreement, pull-up losing to an output, genuine
    contention, and momentary override -- not to reflect anything live.
    """
    return [
        DataCell("PA7", direction="out", local=True, pin=True),
        DataCell("PA6", direction="out", local=True, pin=False),
        DataCell("PA5", direction="out", local=False, pin=True),
        DataCell("PA4", direction="out", local=True, pin=True),
        DataCell("PA3", direction="out", local=False, pin=False),
        DataCell("PA2", direction="in", local=True, pin=True),
        DataCell("PA1", direction="in", local=False, pin=True, momentary_pressed=True),
        DataCell("PA0", direction="in", local=False, pin=False),
        ControlCell("CA1", direction="in", mode="pulse", polarity="rising"),
        ControlCell("CA2", direction="out", mode="level", polarity="falling"),
    ]


def draw_status_bar(surf, fonts, title: str, width: int) -> None:
    """Status-bar chrome: title, `emma65` wordmark, OVERLOAD/MODE placeholders.

    OVERLOAD and MODE are static placeholders here -- they get wired up in
    Units 10-11 (contention detection, Free/Guarded mode).
    """
    small = pygame.font.SysFont("Consolas,Menlo,monospace", sc(12))
    pygame.draw.rect(surf, PANEL, (0, 0, width, status_h))
    pygame.draw.line(surf, PANEL_EDGE, (0, status_h), (width, status_h), 1)
    draw_led(surf, sc(24), sc(20), sc(8), on=False)
    draw_text(surf, small, "OVERLOAD", TEXT_DIM, topleft=(sc(40), sc(13)))
    draw_text(surf, small, "MODE: FREE", ACCENT, topleft=(width - sc(160), sc(13)))
    draw_text(surf, fonts.label, title, TEXT, center=(width // 2, sc(20)))
    draw_text(surf, small, "emma65", TEXT_DIM, topleft=(width - sc(46), sc(13)))
