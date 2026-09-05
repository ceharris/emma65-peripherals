# VIA GPIO Playground — UI Mockup Checkpoint 2

Continuation of `via_gpio_playground_ui_checkpoint.md`, which covered the
initial Port A pass (per-cell layout, chevron design, LED/toggle semantics,
polarity icon, sizing). This document picks up from there: relabeling the
mockup to Port B, redesigning the control cells, and adding PB6/PB7's
special-case affordances. Reference implementation: `row_mockup.py` (same
file, evolved in place).

## Control-cell mode selector: toggle + stylized 15-segment display

The pill-shaped PLS/LVL selector from checkpoint 1 is gone. CB1/CB2 (and
PB6, see below) now use:

- An **ordinary toggle switch** — same widget, same size, same vertical
  offset as the PBx local-state toggle — to select Pulse vs. Level mode.
  On = Pulse, off = Level. (This mapping was an arbitrary but explicit
  choice, not derived from anything; flip it if it doesn't match intuition
  once this is live.)
- A **3-digit "15-segment" display** below the toggle, reading `PUL` or
  `LVL`, driven directly by the toggle above it (not an independent
  control).

**Why the pill was dropped**: reusing the toggle widget means the mode
selector no longer needs its own bespoke shape or its own on/off visual
language — it's legible for free, from the same shape vocabulary already
established for local-pull state elsewhere in the row.

**The segment display is a stylized stand-in, not real segment geometry.**
It's a dark backlit rect (`SEG_BG`) with bold monospace text in an
LED/VFD-style amber (`SEG_ON`), auto-sized tightly around the rendered text
rather than a fixed box. This reads as "digital display" at mockup
fidelity but does not compute actual per-glyph 15-segment strokes. If this
needs to hold up at higher fidelity or larger scale later, that's real
follow-on work, not a tweak.

## Cell height and momentary alignment

All cells (data and control) share one height, sized to fit CB1/CB2's
taller toggle+display+polarity stack. Momentary buttons across the entire
row — PBx and CBx alike — are now vertically aligned to a single offset.
This was a two-step fix: cell height first grew to fit the control cells'
new content, which initially left the *extra* room trailing below the PBx
momentary buttons (dead space at the bottom of the shorter data-cell
stacks); moving the momentary buttons down to match the control cells'
offset relocated that same slack to *between* the toggle and the momentary
button instead — which is what makes it usable as the "gap" that PB6's
display and PB7's speaker icon now occupy.

## Control-cell width equalized to data-cell width

CB1/CB2 dropped from 92px to 40px (pre-scale), matching PBx exactly. This
was possible because the pill's removal and the polarity icon's narrowing
(44px → 30px, to fit the incoming 40px cell) removed the two things that
had required the extra width in the first place.

**Distinguishing control cells from data cells now rests entirely on
spacing.** A dedicated gap (`ctrl_group_gap`, 14px pre-scale) was added
between the last data cell (PB0) and the first control cell (CB1) — the
only remaining visual cue that these are a different kind of cell, now
that width no longer does that job. **Open concern**: this is a weaker cue
than width was. If the panel needs to narrow further (multiple ports
stacked, a smaller window), spacing alone may not hold up and this could
need a stronger cue — a divider line or a subtle background tint are the
likely candidates.

## Port B relabel + PB6 pulse-counting case

All labels moved from Port A to Port B (`PB7`…`PB0`, `CB1`, `CB2`), and the
mockup now depicts the specific configuration used when **PB6 is set up
for negative-edge pulse counting**:

- Pulse counting on PB6 requires the line be forced pulled up — the panel
  no longer needs (or offers) a pull-direction choice for this pin.
- That frees up PB6's toggle, which is **repurposed** to drive the same
  Pulse/Level mode-select + display used on the control cells, rather than
  local pull direction.
- PB6 keeps its full data-cell anatomy otherwise (LED, chevron, momentary)
  — only the toggle's *meaning* changed, not its position or appearance.

**Open concern, not yet resolved**: PB6's LED is still wired to
`cfg["local"]`, hardcoded `True` to represent "forced pulled up." That
field's meaning has silently forked — for every other PBx cell it means
"which way the toggle is pulling," but for PB6 it's now a fixed fact about
the hardware configuration, not something the toggle sets. Nothing in the
mockup currently marks that distinction. This is the same class of problem
checkpoint 1 flagged for the control-cell chevron (an always-outlined
placeholder that's visually indistinguishable from a genuine low-pin-state
reading) — worth a shared solution rather than solving it twice,
independently, per cell type.

## PB7 audio-routing (speaker) indicator

PB7 gained a new indicator — audio-channel routing on/off — occupying the
same gap PB6's display uses. Design went through two passes:

1. **First attempt**: a circular icon-button (matching the momentary
   button's shape language: circle, glow-when-active) with a speaker glyph
   inside. Rejected by human review — didn't read as a speaker at cell
   scale, too much crammed into too small a badge.
2. **Second attempt**, modeled directly on a reference speaker icon (box +
   flared cone + wave arcs, no background chrome): rebuilt as a bare
   polygon glyph, same "no button, just the shape" treatment already used
   by the chevron and the polarity icon. This read clearly.

**Muted state**: simplified per instruction from a small "mute X" (the
Feather/Lucide `volume-x` convention) to a single diagonal line across the
glyph. First implementation of that line used the same dim color as the
icon's fill, so it only became visible where it extended past the icon's
own silhouette — it read as a stray floating mark, not a slash through the
icon. Fixed by drawing the line in a brighter, contrasting color (`TEXT`
instead of `TEXT_DIM`) against the dimmed fill. This was caught only by
actually rendering and looking at the off state, not by reasoning about
the code — worth remembering as a general lesson for any icon with an
on/off pair: render both states before calling either one settled.

**Alignment and centering**: the speaker icon is vertically aligned with
the control cells' polarity icon (both are single-item occupants of the
toggle-to-momentary gap, and now share one offset constant). Horizontally,
it's centered in the cell *including the wave arcs* — the box+cone
silhouette alone is symmetric, but the arcs only extend rightward from the
apex, so centering the box+cone's own midpoint left the on-state glyph
visibly off-center. The fix centers the full bounding box for whichever
state is being drawn (arcs included, when present), which means the
box+cone shifts slightly left in the "on" state to leave room for the
arcs on the right. Verified against actual rendered pixel bounds, not just
visually: on-state glyph center lands within a pixel of the cell's true
center.

**Color**: a dedicated hue (`SPKR_ON`, violet) rather than reusing
anything already in the palette — LED green, direction blue/orange, and
accent gold are all already carrying other meanings (gold in particular is
double-booked between momentary-press glow and the segment display text).

**Open concern**: the wave arcs are sized tightly against the 40px
(pre-scale) cell width — they reach to within about a pixel and a half of
the cell edge in the "on" state. This is the first element that will need
to shrink, or drop an arc, if the cell ever needs to narrow further.

## Scaling the whole mockup to 600px

The single-port row's actual content width (measured, not estimated) was
468px. Rather than hand-adjusting every dimension to make room for a
second port, the whole mockup was rescaled uniformly by a factor
`S = 600 / 468`, via a single `sc(v)` helper that every position, size,
radius, and font size in the file now passes through. Two ports side by
side at this scale comfortably fit a typical workstation display.

**Why a scale factor instead of hand-tuning**: retuning the entire
mockup's fidelity later — for a different target width, a different
display, or a second port — becomes a one-line change (`S = ...`) instead
of a pass through every magic number in the file.

## Canvas margins — derived, not guessed

Fixed while equalizing PB7's left margin against CB2's right margin.
Previously the canvas was sized to a fixed guessed constant
(`sc(520)`) independent of the actual laid-out content, and — a latent
ordering bug — canvas creation happened *before* the layout constants that
determine content width were even defined. Left and right margins had no
reason to match and didn't.

**Fix**: the per-cell layout pass was pulled into a `layout_row(start_x)`
function, used two ways — once with `start_x = 0` purely to measure
content width, then again with `start_x = LEFT_MARGIN` to actually draw.
Canvas width is derived as `LEFT_MARGIN + content_width + LEFT_MARGIN`.
Margins are now guaranteed symmetric by construction, and — because both
the measurement pass and the drawing pass go through the same function —
they can't silently drift apart from each other as the pin list changes.
Verified against rendered pixels: both margins measure exactly 26px at
current scale.

## Open questions carried forward from checkpoint 1

Still unresolved, unchanged since the first checkpoint:

- Minimum tappable/clickable size for the toggle and momentary controls at
  the current (narrow) cell width.
- Whether cell-level contention (output pin, genuine short) warrants its
  own visual cue distinct from the ordinary pull-up-loses-to-output case,
  versus relying solely on the aggregate status-bar Overload indicator.
- Computing CA1/CA2/CB1/CB2 direction from live ACR/PCR state instead of
  the current hardcoded placeholder.
- Visually disambiguating a control cell's placeholder outlined chevron
  from a data cell's genuine low-pin-state reading.

## New open questions from this iteration

- **PB6's LED/local-state ambiguity** (detailed above) — needs a visual
  cue or a documented decision distinguishing "toggle-driven" from
  "fixed-by-configuration" before more repurposed-widget cells are added.
- **Data/control cell distinction now relies solely on spacing** — no
  longer backed by a width difference. Revisit if the panel needs to
  narrow.
- **Ordinary PBx cells (not PB6/PB7) still carry dead space** between the
  toggle and momentary button, since only the special-case cells fill that
  gap. Still an open call whether to leave this as breathing room or
  redistribute it — not addressed this iteration.
- **Speaker icon's tight fit** against the cell edge (noted above) — first
  casualty of any further narrowing.
- **Assumed on/off conventions** — toggle-on-means-Pulse, and
  speaker-glyph-on-means-routed — were both introduced as explicit but
  arbitrary choices and haven't been confirmed against how this will
  actually be driven from live VIA state.

## Next steps

- Mock up PB7's T1-free-run indicator, following whatever visual pattern
  gets settled on for "special-case cell carries an extra gap-filling
  widget" (PB6 and PB7 have each independently invented one so far — worth
  converging before a third one shows up).
- Translate the settled visual language into the `Cell` base class /
  `DataCell` / `ControlCell` hierarchy, with `PB6Cell` / `PB7Cell` as thin
  decorators — more pressing now than at checkpoint 1, since the row has
  grown to four distinct cell subtypes (plain data, mode-select data, and
  two control-cell variants) all still living in one flat per-pin dict.
- Bring Port A into the same canvas as Port B. The row-drawing logic
  (`layout_row` plus the per-cell drawing block) needs to become a
  function parameterized by a starting position, so the two ports are one
  reused block rather than two copies that can drift out of sync.
- Resolve the open concerns above — particularly PB6's LED semantics and
  the control-chevron placeholder ambiguity — before they compound further
  as more special-case cells accumulate.
- Wire up real interactivity (momentary press/release, toggle click) once
  the static layout is finalized, since several open decisions (momentary
  override duration, contention display) only fully make sense once the
  panel is live rather than a static frame.
