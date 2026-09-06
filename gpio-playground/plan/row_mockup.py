import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
import math

pygame.init()

# ---- Palette ----
BG          = (22, 24, 28)
PANEL       = (32, 35, 40)
PANEL_EDGE  = (52, 56, 62)
TEXT        = (215, 218, 222)
TEXT_DIM    = (140, 145, 152)
LED_HIGH    = (86, 214, 128)
LED_LOW     = (60, 64, 70)
LED_FAULT   = (232, 168, 56)
DIR_IN      = (86, 156, 232)
DIR_OUT     = (214, 122, 86)
TOGGLE_ON   = (86, 214, 128)
TOGGLE_OFF  = (58, 62, 68)
BTN         = (70, 75, 82)
BTN_EDGE    = (98, 104, 112)
ACCENT      = (244, 196, 92)
STATUS_OK   = (86, 214, 128)

# "15-segment" mode display — stylized stand-in, not real per-glyph segment
# geometry. Dark backlit rect + bold monospace text in an LED/VFD-style
# amber. Good enough to read as "digital display" at mockup fidelity.
SEG_BG    = (12, 12, 14)
SEG_ON    = (255, 153, 51)

# Speaker/audio-routing indicator — a distinct hue from everything else in
# the palette (LED green, direction blue/orange, accent gold) so "this pin
# is routed to audio" reads as its own category at a glance.
SPKR_ON   = (176, 141, 235)

# ---- Global scale ----
# All layout constants below are defined at a base fidelity tuned for a
# ~468px-wide single-port row, then multiplied by S. Two ports side by side
# at this scale comfortably fit a typical workstation display; retuning the
# whole mockup later is a single-number change here rather than a pass
# through every magic number in the file.
S = 600 / 468

def sc(v):
    return round(v * S)

# ---- Row layout constants ----
# (defined before the canvas so the canvas width can be derived from the
# actual laid-out content rather than guessed and hardcoded)
chevron_size = sc(28)  # matches LED diameter
label_center_y = sc(66)      # PBx / CBx label, floats above everything
chevron_y0 = label_center_y + sc(12)
row_y = chevron_y0 + chevron_size + sc(10)   # cell top, below the chevron
cell_h = sc(200)   # cell height stays keyed to CB1/CB2's stack; PBx momentary
                   # now sits at the same offset as the control cells' (below),
                   # so the extra room shows up as a gap above the button
ctrl_w = sc(40)    # no longer needs to be wider than the data cells — the
                   # level/pulse toggle+readout replaced the pill, and the
                   # polarity icon narrowed to fit — so CB1/CB2 now match PBx
data_w = sc(40)
gap = sc(6)
ctrl_group_gap = sc(14)   # extra space before CB1, setting the control pair
                          # apart from the PBx data cells
LEFT_MARGIN = sc(20)      # mirrored on the right so PB7 and CB2 sit the
                          # same distance from their respective canvas edges

# per-cell vertical offsets (from rect.top), shared across the row so that
# widgets of the same kind line up regardless of which cell they're in
LED_OFF_DATA   = sc(30)
LED_OFF_CTRL   = sc(26)
TOGGLE_OFF     = sc(76)
SEG_OFF        = sc(104)
POLARITY_OFF   = sc(135)   # also used for PB7's speaker icon — see below
MOMENTARY_OFF  = sc(170)

# ---- Legend ----
# "local" = the level the toggle switch is set to pull the pin toward (this
# is also what the toggle widget itself displays: on = pulled high).
# "pin" = the actual resultant node level the VIA sees — shown by the
# chevron (filled = high, outline = low). For input pins, the panel is the
# only driver, so pin normally equals local — except while the momentary
# button is held, which asserts the opposite level for as long as it's
# pressed. For output pins, the VIA drives the node and can disagree with
# local (pull-up/down losing to an active driver, or genuine contention).
pins = [
    ("PB7", "data", {"dir": "out", "local": True,  "pin": True,     # agree, high; audio
                      "speaker": True}),                            # routing enabled
    ("PB6", "data", {"dir": "in",  "local": True,  "pin": True,     # forced pulled-up (idle high) for
                      "level_mode": "pulse"}),                      # negative-edge pulse counting; toggle
                                                                     # repurposed as PUL/LVL mode select
    ("PB5", "data", {"dir": "out", "local": True,  "pin": False}),  # pull-up loses to VIA driving low (no fault)
    ("PB4", "data", {"dir": "out", "local": False, "pin": True}),   # toggle low + VIA out high = contention
    ("PB3", "data", {"dir": "out", "local": True,  "pin": True}),   # agree, high
    ("PB2", "data", {"dir": "out", "local": False, "pin": False}),  # toggle low, VIA also drives low, agree
    ("PB1", "data", {"dir": "in",  "local": True,  "pin": True}),   # toggle high, pin follows
    ("PB0", "data", {"dir": "in",  "local": False, "pin": True,     # toggle low (idle), but momentary
                      "momentary_pressed": True}),                  # is held -> pin temporarily high
    ("CB1", "ctrl", {"level_mode": "pulse", "polarity": "rising",  "dir": "in"}),
    ("CB2", "ctrl", {"level_mode": "level", "polarity": "falling", "dir": "out"}),
]

def layout_row(start_x):
    # Single source of truth for cell positions — used both to measure the
    # row's content width (so the canvas can center it with equal margins)
    # and to actually draw it, so the two can never drift apart.
    x = start_x
    prev_kind = None
    cells = []
    for name, kind, cfg in pins:
        if prev_kind == "data" and kind == "ctrl":
            x += ctrl_group_gap
        w = ctrl_w if kind == "ctrl" else data_w
        cells.append((name, kind, cfg, pygame.Rect(x, row_y, w, cell_h)))
        x += w + gap
        prev_kind = kind
    return cells, x - gap   # x - gap = right edge of the last cell

_, content_right = layout_row(0)
W, H = LEFT_MARGIN + content_right + LEFT_MARGIN, sc(340)
surf = pygame.Surface((W, H))
surf.fill(BG)

font_label   = pygame.font.SysFont("Consolas,Menlo,monospace", sc(16), bold=True)
font_small   = pygame.font.SysFont("Consolas,Menlo,monospace", sc(12))
font_tiny    = pygame.font.SysFont("Consolas,Menlo,monospace", sc(10))
font_seg     = pygame.font.SysFont("Consolas,Menlo,monospace", sc(13), bold=True)

def draw_text(text, font, color, center=None, topleft=None):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center: rect.center = center
    if topleft: rect.topleft = topleft
    surf.blit(img, rect)
    return rect

def draw_led(cx, cy, r, on):
    color = LED_HIGH if on else LED_LOW
    if on:
        glow_r = int(r * 1.6)
        glow = pygame.Surface((glow_r*2, glow_r*2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*color, 70), (glow_r, glow_r), glow_r)
        surf.blit(glow, (cx - glow_r, cy - glow_r))
    pygame.draw.circle(surf, color, (cx, cy), r)
    pygame.draw.circle(surf, (0,0,0,255), (cx, cy), r, 1)

def draw_toggle(cx, cy, w, h, on):
    rect = pygame.Rect(0,0,w,h)
    rect.center = (cx, cy)
    pygame.draw.rect(surf, TOGGLE_ON if on else TOGGLE_OFF, rect, border_radius=h//2)
    knob_x = rect.right - h//2 if on else rect.left + h//2
    pygame.draw.circle(surf, (240,240,240), (knob_x, cy), h//2 - 2)

def draw_momentary(cx, cy, r, pressed=False):
    body = ACCENT if pressed else BTN
    edge = ACCENT if pressed else BTN_EDGE
    if pressed:
        glow_r = int(r * 1.6)
        glow = pygame.Surface((glow_r*2, glow_r*2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*ACCENT, 70), (glow_r, glow_r), glow_r)
        surf.blit(glow, (cx - glow_r, cy - glow_r))
    pygame.draw.circle(surf, body, (cx, cy), r)
    pygame.draw.circle(surf, edge, (cx, cy), r, 2)
    pygame.draw.circle(surf, (0,0,0), (cx, cy), max(1, r-6), 1)

def draw_chevron(cx, y0, size, direction, pin_high):
    # direction: 'in' (apex up) | 'out' (apex down). Filled = pin state high,
    # outline = pin state low. This is the actual node level the VIA sees.
    color = DIR_IN if direction == "in" else DIR_OUT
    half = size / 2
    if direction == "in":
        points = [(cx - half, y0 + size), (cx + half, y0 + size), (cx, y0)]
    else:
        points = [(cx - half, y0), (cx + half, y0), (cx, y0 + size)]
    if pin_high:
        pygame.draw.polygon(surf, color, points)
    else:
        pygame.draw.polygon(surf, color, points, width=2)

def draw_seg_display(cx, cy, text, color=SEG_ON, pad_x=None, pad_y=None):
    # Auto-sized to the text plus a tight pad, rather than a fixed box —
    # keeps the footprint as small as the 3-char content allows.
    pad_x = sc(3) if pad_x is None else pad_x
    pad_y = sc(2) if pad_y is None else pad_y
    text_w, text_h = font_seg.size(text)
    w, h = text_w + pad_x * 2, text_h + pad_y * 2
    rect = pygame.Rect(0, 0, w, h)
    rect.center = (cx, cy)
    pygame.draw.rect(surf, SEG_BG, rect, border_radius=3)
    pygame.draw.rect(surf, PANEL_EDGE, rect, width=1, border_radius=3)
    draw_text(text, font_seg, color, center=rect.center)
    return rect

def draw_speaker_icon(cx, cy, on, scale=1.0):
    # Modeled directly on a standard speaker glyph: a narrow box flaring
    # into a wide cone, with wave arcs off the apex when routing is on.
    # No background badge — same "bare shape" treatment as the chevron and
    # polarity icon elsewhere in the cell.
    #
    # The box+cone silhouette alone is horizontally symmetric, but the wave
    # arcs only extend rightward from the apex — so centering the box+cone
    # at cx (as before) left the whole glyph, arcs included, visibly
    # off-center when routing was on. Instead, size the full bounding box
    # for the current state (arcs included, when present) and center *that*
    # at cx, so the box+cone shifts left to make room for the arcs on the
    # right rather than the arcs just hanging further out on one side.
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
        # muted: a single diagonal stroke across the whole glyph. Needs
        # contrast against the dimmed fill (TEXT_DIM), not just against the
        # background — same color as the fill made it read as a stray mark
        # poking out above/below the shape rather than a slash through it.
        lw = max(2, int(3 * scale))
        pygame.draw.line(surf, TEXT, (x0, cy - apex_h), (apex_x, cy + apex_h), lw)

def draw_pulse_icon(cx, cy, w, h, polarity):
    # Polarity here doubles as the pull direction: "rising" = pulled down
    # (idle low, a brief high pulse), "falling" = pulled up (idle high, a
    # brief low pulse). The first (active) edge is bold/colored; the return
    # edge back to idle stays dim.
    active = DIR_IN if polarity == "rising" else DIR_OUT
    bottom_y = cy + h / 2
    top_y = cy - h / 2
    x0 = cx - w / 2
    x1 = x0 + w * 0.32
    x2 = x0 + w * 0.68
    x3 = cx + w / 2
    if polarity == "rising":
        idle_y, excursion_y = bottom_y, top_y   # idle low, brief high
    else:
        idle_y, excursion_y = top_y, bottom_y   # idle high, brief low
    pygame.draw.line(surf, TEXT_DIM, (x0, idle_y), (x1, idle_y), 1)
    pygame.draw.line(surf, active,   (x1, idle_y), (x1, excursion_y), 3)
    pygame.draw.line(surf, TEXT_DIM, (x1, excursion_y), (x2, excursion_y), 1)
    pygame.draw.line(surf, TEXT_DIM, (x2, excursion_y), (x2, idle_y), 1)
    pygame.draw.line(surf, TEXT_DIM, (x2, idle_y), (x3, idle_y), 1)

# ---- Status bar ----
status_h = sc(40)
pygame.draw.rect(surf, PANEL, (0, 0, W, status_h))
pygame.draw.line(surf, PANEL_EDGE, (0, status_h), (W, status_h), 1)
draw_led(sc(24), sc(20), sc(8), on=False)
draw_text("OVERLOAD", font_small, TEXT_DIM, topleft=(sc(40), sc(13)))
draw_text("MODE: FREE", font_small, ACCENT, topleft=(W - sc(160), sc(13)))
draw_text("PORT B", font_label, TEXT, center=(W//2, sc(20)))
draw_text("emma65", font_small, TEXT_DIM, topleft=(W - sc(46), sc(13)))

# ---- Row of cells ----
cells, _ = layout_row(LEFT_MARGIN)
for name, kind, cfg, rect in cells:
    # module; the label+chevron pair above it is what ties it to a specific pin
    draw_text(name, font_label, TEXT, center=(rect.centerx, label_center_y))

    # chevron: connects the label to its cell. For data pins it's a live
    # pin-state indicator (filled/outline); for control pins, direction is
    # context-dependent on ACR/PCR, so for now it's always outlined — just a
    # label-to-cell connector with a direction hint, not a state readout.
    if kind == "data":
        draw_chevron(rect.centerx, chevron_y0, chevron_size, cfg["dir"], cfg["pin"])
    else:
        draw_chevron(rect.centerx, chevron_y0, chevron_size, cfg["dir"], False)

    # panel background
    pygame.draw.rect(surf, PANEL, rect, border_radius=10)
    pygame.draw.rect(surf, PANEL_EDGE, rect, width=1, border_radius=10)

    if kind == "data":
        draw_led(rect.centerx, rect.top + LED_OFF_DATA, sc(13), on=cfg["local"])
        if "level_mode" in cfg:
            # PB6-in-pulse-counting-mode case: the toggle no longer sets
            # pull direction (the line is forced pulled up), so it's
            # repurposed to drive the same PUL/LVL mode select + readout
            # used on the control cells.
            mode = cfg["level_mode"]
            draw_toggle(rect.centerx, rect.top + TOGGLE_OFF, sc(28), sc(15), on=(mode == "pulse"))
            seg_text = "PUL" if mode == "pulse" else "LVL"
            draw_seg_display(rect.centerx, rect.top + SEG_OFF, seg_text)
        else:
            draw_toggle(rect.centerx, rect.top + TOGGLE_OFF, sc(28), sc(15), on=cfg["local"])
        if "speaker" in cfg:
            # PB7's audio-routing indicator — vertically aligned with the
            # control cells' polarity icon so the row's single-item gap
            # fillers all land on the same line regardless of cell type.
            draw_speaker_icon(rect.centerx, rect.top + POLARITY_OFF, on=cfg["speaker"], scale=S)
        # aligned with the control cells' momentary so the extra row height
        # shows up as a gap above the button, not below it
        draw_momentary(rect.centerx, rect.top + MOMENTARY_OFF, sc(12), pressed=cfg.get("momentary_pressed", False))
    else:
        draw_led(rect.centerx, rect.top + LED_OFF_CTRL, sc(12), on=False)

        # level/pulse mode toggle — same widget as the PBx local-state
        # toggle, same size, positioned at the same offset for cross-row
        # alignment. on = pulse, off = level.
        mode = cfg["level_mode"]
        draw_toggle(rect.centerx, rect.top + TOGGLE_OFF, sc(28), sc(15), on=(mode == "pulse"))

        # mode readout — stylized 15-segment-style display, driven by the
        # toggle above it (not an independent control)
        seg_text = "PUL" if mode == "pulse" else "LVL"
        draw_seg_display(rect.centerx, rect.top + SEG_OFF, seg_text)

        # polarity icon — single-pulse waveform, active edge bold/colored.
        draw_pulse_icon(rect.centerx, rect.top + POLARITY_OFF, sc(30), sc(16), cfg["polarity"])

        draw_momentary(rect.centerx, rect.top + MOMENTARY_OFF, sc(13), pressed=False)

pygame.image.save(surf, "/home/claude/row_mockup.png")
print("saved", W, H)
