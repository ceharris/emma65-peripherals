# VIA GPIO Playground — UI Mockup Checkpoint

Companion to `via_gpio_playground_design.md`. That doc specifies the panel's
behavior; this one captures the visual-design decisions made while mocking up
a single row (Port A) in Pygame, including alternatives that were tried and
rejected. Reference implementation: `row_mockup.py`.

## Per-cell layout (settled)

Each pin cell is a small vertical module, generic in structure regardless of
which physical pin it represents:

- **Label** (e.g. `PA7`), floating above everything else.
- **Chevron**, directly below the label, roughly diameter-matched to the LED.
  This is the connective visual tie between an abstract, interchangeable cell
  body and the specific pin it's currently bound to.
- **Cell body** (rounded-rect panel): LED, then toggle, then momentary
  button, top to bottom. No text labels on the widgets themselves — their
  function is legible from shape alone (toggle vs. round pushbutton).

Data cells (PA0–PA7) and control cells (CA1/CA2, and by extension CB1/CB2)
share this same label → chevron → body structure, which is deliberate: it
reinforces that the cell is a generic module and the header is what
specializes it to a given pin.

## Chevron: direction + live pin state

The chevron does double duty:

- **Shape/color = direction.** Apex-up + blue = input. Apex-down + orange =
  output.
- **Fill = the actual node level the VIA sees** ("pin" state — the same
  concept as the design doc's "state LED," just relocated). Filled = high,
  outline = low.

This replaced an earlier direction indicator that was a colored border drawn
*inside* the cell rect; moving it outside and enlarging it to LED-diameter
size both reads better at a glance and frees it to double as the pin-state
indicator.

### Rejected alternative: two LEDs (local + pin)

Before settling on the chevron-as-pin-state approach, we tried giving each
data cell two LEDs side by side — one for "local" (what the panel's own
toggle/momentary/pull-up alone is asserting) and one for "pin" (the actual
node level). This was explicitly tried and **rejected as more detrimental
than beneficial** — it added visual clutter and a redundant circle without
adding clarity the chevron couldn't provide once repurposed. Don't
reintroduce a second LED without revisiting why this was dropped.

## LED = "local" state, and how it relates to the toggle/momentary

The single LED reflects **local** state: the level the panel's own toggle is
set to pull the pin toward. Critically, the toggle switch's on/off directly
*is* that local state — toggle on = pulling high, toggle off = pulling low.
(An earlier draft had the toggle's on-state inverted relative to local; this
was a bug, not a design choice, and was corrected.)

- **Input pins:** the panel is the sole driver, so pin state normally equals
  local state — LED and chevron agree. Pressing the momentary button
  temporarily asserts the *opposite* level for as long as it's held,
  regardless of toggle position; the mockup shows this by lighting the
  momentary button itself (glow, accent color) and filling/outlining the
  chevron to the overridden value. This is the interactive behavior a real
  implementation needs to wire up: momentary-press state must be able to
  override toggle-derived pin state for the duration of the press.
- **Output pins:** the VIA drives the node, so pin state can legitimately
  diverge from local state. Two distinct cases are worth keeping distinct in
  future iterations:
  - *Expected divergence, not a fault*: the panel's pull-up/pull-down loses
    to an actively driven VIA output (e.g. local wants high via pull-up, VIA
    output drives low — pin follows the VIA, LED stays as the panel's own
    intent).
  - *Genuine contention*: the panel's toggle is actively asserting one level
    while the VIA output pin drives the opposite level — a real short. The
    mockup treats this exactly like the expected-divergence case visually
    (LED/chevron mismatch is the only cue) per the design doc's decision not
    to auto-suppress switches in Free mode. Whether cell-level contention
    should get its own visual treatment (vs. relying solely on the aggregate
    Overload indicator in the status bar) is still open — see below.

## Control-cell chevron: intentionally a placeholder

CA1/CA2 (and by extension CB1/CB2) also get the label+chevron treatment for
visual consistency with data cells, but the chevron here is **always
outlined**, regardless of any level/state — it currently encodes direction
only (CA1 = input/up/blue, CA2 = output/down/orange), not a live reading.

This is a deliberate placeholder, not a finished design: control-line
direction is context-dependent on ACR/PCR configuration, and working out
that logic was explicitly deferred rather than resolved in this pass. Two
consequences worth flagging for later:

- The direction shown for CA1/CA2 (and CB1/CB2) needs to eventually be
  computed from ACR/PCR state rather than hardcoded.
- An always-outlined control chevron currently looks visually identical to a
  data-pin chevron reading "pin is low." That ambiguity should probably get
  a secondary cue (e.g. dashed outline, distinct color, or a small
  placeholder glyph) before this becomes real, so users don't misread it as
  a live low-state reading.

## Polarity indicator: pulse-graph icon

Replaced a simple up/down arrow with a small line-graph pulse icon, because
the polarity setting is really describing pull direction, not just an
abstract edge:

- **Rising polarity = pulled down**: idle low, with a brief high excursion.
- **Falling polarity = pulled up**: idle high, with a brief low excursion.

The first (active-edge) transition is drawn bold and colored (blue for
rising/pulled-down, orange for falling/pulled-up); the return-to-idle
transition stays thin and dim. This makes the icon read as "here's what this
pin's brief pulse looks like" rather than an abstract direction glyph.

## Sizing

- PAx cells were narrowed twice over the course of the mockup (108px →
  80px → 40px), converging on "just a little wider than the chevron base"
  rather than a fixed percentage — the chevron's footprint (28px) is the
  actual constraint, not an arbitrary target width.
- CA1/CA2 stayed noticeably wider (92px) — this is **intentional**, not
  leftover from before the data cells shrank. The pulse-mode pill and
  polarity icon need the room to avoid feeling cramped.
- LED glow ring was scaled down from a very prominent 4×-radius halo to a
  subtler 1.6×-radius one; same treatment now reused for the momentary
  button's "pressed" glow. (Reduced again during Unit 5's real-code
  iteration to 1.3× -- see `cells.GLOW_RADIUS_SCALE`, shared by `draw_led`
  and `draw_momentary` so the two stay in sync.)

## Open questions / not yet addressed

- Minimum tappable/clickable size for the toggle and momentary controls at
  the current (narrow) cell width — flagged but not evaluated.
- Whether cell-level contention (output pin, genuine short) warrants its own
  visual cue distinct from the ordinary pull-up-loses-to-output case, versus
  relying solely on the aggregate status-bar Overload indicator.
- Computing CA1/CA2/CB1/CB2 direction from live ACR/PCR state instead of the
  current hardcoded placeholder.
- Visually disambiguating a control cell's placeholder outlined chevron from
  a data cell's genuine low-pin-state reading.
- PB6/PB7 special-case affordances (pulse-mode indicator, T1-driving-PB7
  indicator) haven't been mocked up yet — deferred to the Port B pass.

## Next steps

- Mock up Port B, including PB6 (pulse-mode indicator layered on the
  standard data cell) and PB7 (T1-free-run indicator layered on the standard
  data cell), per the design doc's "layered capability, not a replacement"
  framing.
- Translate the settled visual language into the `Cell` base class /
  `DataCell` / `ControlCell` hierarchy discussed earlier, with `PB6Cell` /
  `PB7Cell` as thin decorators rather than separate cell types.
- Wire up real interactivity (momentary press/release, toggle click) once
  the static layout is finalized, since several of the above decisions
  (momentary override duration, contention display) only fully make sense
  once the panel is live rather than a static frame.
