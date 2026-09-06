# VIA GPIO Playground — Implementation Plan

This is an agent-ready sequence of work units for implementing the VIA GPIO
playground peripheral. It turns the settled design
(`via_gpio_playground_design.md`) and visual language
(`via_gpio_playground_ui_checkpoint.md`, `via_gpio_playground_ui_checkpoint_2.md`,
`row_mockup.py`) into working software, one reviewable PR at a time.

## How to use this plan

- **Read the three design docs before starting any unit.** They record
  decisions already made and alternatives already tried and rejected (e.g.
  the two-LED-per-cell approach, the pill-shaped mode selector). Don't
  re-litigate those; implement what they settled on.
- **One unit = one PR.** Units are ordered so each one leaves the repo in a
  working, demonstrable state — don't reach ahead into a later unit's scope
  even if it looks convenient.
- **Where a design doc explicitly left something open** (marked "open
  concern," "deferred," or "TBD" in the checkpoints), the unit below says so
  and either (a) tells you which unit resolves it, or (b) tells you to make
  a documented judgment call at that point, consistent with the project's
  "no half-finished implementations" norm — pick a reasonable behavior and
  note it in the PR description rather than leaving a TODO.
- **Unit 0 establishes pytest + CI; every unit after it should add tests
  alongside new logic where it's practical to do so** (protocol parsing,
  contention/direction models, snapshot serialization — anything that
  isn't fundamentally "does pygame draw the right pixels," which stays a
  manual-verification concern). Each unit still lists a manual
  verification recipe for the parts that can't reasonably be
  unit-tested (rendering, live-socket interaction, audio output).
- Follow `CLAUDE.md`'s peripheral conventions throughout: a peripheral never
  touches port bits it isn't explicitly configured to drive, and reconnects
  must re-assert current state (see `ButtonPeripheral.connect_if_needed` in
  `buttons/src/emma65_buttons/app.py` for the established pattern).

## New package

The design docs describe a peripheral distinct from `buttons`; `gpio-playground/`
itself is a planning/mockup scratch area (per `CLAUDE.md`), not the package.
Unit 2 creates a new top-level workspace member, suggested name **`via-playground/`**
(distribution name `emma65-via-playground`), following the same shape as `buttons/`.
Rename it before or during Unit 2 if a better name occurs to you — nothing
downstream depends on the name yet.

## Dependency overview

Units run in listed order. Rough grouping:

- **0**: testing/CI scaffolding, prerequisite to everything else.
- **1–2**: foundations (protocol read-side, empty peripheral skeleton).
- **3–7**: core panel — full Port A (data + control), then Port B joins in
  the same window. This is the "all pins observable and manipulable" MVP.
- **8–9**: PB6/PB7 hardware-specific layered behavior, including audio.
- **10–11**: contention detection and the Free/Guarded mode switch.
- **12–14**: the design doc's explicitly-scoped extended features (bounce
  modeling, waveform trace, presets/snapshots).
- **15**: cleanup pass over accumulated open concerns.

Each unit below states its direct prerequisites.

---

## Unit 0 — Testing and CI scaffolding

**Depends on:** nothing.

**Problem:** the workspace has no lint/test/CI tooling configured today,
and this plan is about to add ~15 PRs of new logic (protocol parsing,
direction/contention models, snapshot serialization) that's much cheaper
to get right with real unit tests than with manual verification alone.
This unit stands up the minimum viable harness before any of that lands,
so every later unit can add tests as it goes instead of retrofitting them.

**Scope:**
- Add `pytest` as a dev-dependency. Since this is a `uv` workspace, prefer
  a workspace-level dev-dependency group (root `pyproject.toml`) so a
  single `uv run pytest` from the root discovers tests across all member
  packages, rather than requiring a separate invocation per package.
- Establish the test-layout convention each package will follow — a
  `tests/` directory alongside each package's `src/` (e.g.
  `via/tests/test_ascii_client.py`) is the natural fit for this workspace
  shape; pick that or an equivalent and note it so later units don't each
  invent their own.
- Prove the harness actually works end-to-end by adding a handful of real
  tests for **existing, currently-untested code** — don't leave this unit
  as an empty scaffold with nothing exercising it:
  - `emma65_via.ViaAsciiClient`: `set_bits`/`reset_bits` message framing
    (e.g. mock or a real connected `socketpair()` to assert the exact
    bytes sent), and `connect()` returning `False` against a socket path
    that doesn't exist.
  - `emma65_buttons.ButtonPeripheral`: the push/toggle bit-mask logic and
    reconnect re-assertion behavior, which are pure enough to test without
    a real VIA emulator on the other end.
- Add a minimal GitHub Actions workflow (`.github/workflows/ci.yml`) that
  runs on push/PR: `uv sync` then `uv run pytest`. Keep it to just that —
  don't add lint/type-check/coverage gates in this unit; those are
  separate calls the user hasn't asked for yet, and adding them
  unrequested would be scope creep on what's meant to be a lightweight
  prerequisite.

**Manual verification:** `uv run pytest` passes locally from the repo
root; push the branch and confirm the GitHub Actions workflow actually
runs and passes on the PR (and, ideally, confirm it *fails* on a
deliberately broken test first, so you know the wiring is real and not a
workflow that silently no-ops).

---

## Unit 1 — VIA protocol read-side support in `emma65-via`

**Depends on:** Unit 0.

**Problem:** `ViaAsciiClient` (`via/src/emma65_via/ascii_client.py`) is
write-only today — `drain()` discards every inbound byte. The playground
needs to *observe* VIA state: which way each pin is currently driven, its
live level, and (for later units) DDR/ACR/PCR register contents. None of
that is possible with the client as it stands.

**Scope:**
- Investigate the actual VIA peer protocol wire format for whatever
  inbound messages the emulator sends to peers — port-level change
  notifications and/or register-state reports. This lives in the
  `emma65-rust` project's protocol documentation/source, not in this repo;
  consult it (or the user, if it's not readily available) before writing
  code. Don't guess at a wire format.
- Extend `emma65_via` with a parsing/event layer alongside the existing
  send-only calls — for example, a `poll() -> list[ViaEvent]` that replaces
  (or wraps) `drain()`, decoding recognized inbound messages into typed
  events (port bit level changes at minimum; register-state events if the
  protocol reports DDR/ACR/PCR directly — otherwise note that as a gap for
  a later unit to revisit).
  - Whichever behaviors later units need to observe (direction, live level,
    T1/T2 mode bits) must eventually be derivable from something Unit 1
    exposes. It's fine if Unit 1 only covers what the protocol reports
    up front, and later units (6, 8, 9, 10) extend this module when they
    hit a register they need that isn't covered yet — call that out
    explicitly in those units' PRs rather than silently working around it.
- Keep `set_bits`/`reset_bits`/`connect`/`close` unchanged; this is additive.
- Update `via/README.md` (or add one) describing the new read-side API.
- Add unit tests for the new parsing/event logic (per Unit 0's `tests/`
  convention) — this is pure decode logic, well-suited to feeding it
  canned byte sequences and asserting the resulting events, without
  needing a live socket.

**Manual verification:** beyond the unit tests, a small throwaway script
connecting to a live (or test-harness) VIA socket, toggling a pin from
the emulator side, and printing decoded events — include the script or
its equivalent steps in the PR description, since exercising a real
socket end-to-end is still worth doing even with unit coverage in place.

---

## Unit 2 — New peripheral skeleton

**Depends on:** Unit 1 (imports `emma65_via`, though this unit may not yet
use the new read-side calls).

**Scope:**
- New top-level package (`via-playground/`, see above) with its own
  `pyproject.toml` (`emma65-via` as a workspace source, `pygame-ce`
  dependency), following `buttons/pyproject.toml`'s shape.
- `app.py` with `parse_args` (at minimum `--socket`) and a `Peripheral`-style
  class that owns a `ViaAsciiClient`, reusing the `connect_if_needed`
  reconnect-with-backoff pattern from `ButtonPeripheral`.
- A pygame window that opens, shows a connection-status readout (connected
  / connecting, same idea as `buttons`' status line), and otherwise draws
  nothing — no pin cells yet. This proves the plumbing end-to-end before
  any rendering complexity is added.
- Register the new peripheral in the root `README.md`.

**Manual verification:** `uv sync && uv run --package emma65-via-playground
emma65-via-playground`, confirm the window opens and connection status flips
correctly against a running (and then stopped) VIA socket.

---

## Unit 3 — Reusable cell-rendering architecture + static Port A row

**Depends on:** Unit 2.

**Scope:**
- Translate the settled visual language from checkpoint 1 (label → chevron
  → cell body; LED, toggle, momentary; no text on widgets) and checkpoint
  2 (equal-width data/control cells, `ctrl_group_gap` spacing cue, the
  scale-factor `sc()` approach, canvas margins derived from measured
  content width) into real, reusable code — not a copy-paste of
  `row_mockup.py`'s drawing calls, but structured as the `Cell` /
  `DataCell` / `ControlCell` class hierarchy both checkpoints call for.
- Build the row layout as a function of a **port** (pin list + starting
  x-position), not hardcoded to one port — Port B (Unit 7) must become a
  second call into the same code, not a duplicated block. This is called
  out explicitly in checkpoint 2 as a risk ("two copies that can drift out
  of sync") — design it out from the start rather than retrofitting later.
- Render Port A (PA0–PA7, CA1, CA2) into the Unit 2 window using **static
  placeholder state** — no live VIA data yet, no interactivity yet. This
  unit is purely "does the settled visual design translate into real
  widget code correctly."
- Include the status bar chrome from `row_mockup.py` (title, `emma65`
  wordmark) but leave the OVERLOAD and MODE indicators as static
  placeholders — they get wired up in Units 10–11.

**Manual verification:** run the peripheral, visually compare the rendered
Port A row against `row_mockup.png` (Port A pass) / the checkpoint 1
description for layout fidelity.

---

## Unit 4 — Live pin-state and direction for Port A data pins

**Depends on:** Unit 3 (rendering), Unit 1 (protocol read events).

**Scope:**
- Wire the chevron for PA0–PA7 to real data: direction from DDRA (per pin
  bit) and live pin level from the read-side events added in Unit 1.
- The LED continues to show *local* state (the panel's own pull), which at
  this point is just a fixed default per pin (e.g. all pulled low) since
  toggle interactivity isn't wired up until Unit 5 — the point of this
  unit is exercising the DDRA/live-level read path, not the write path.
- If DDR readback turns out not to be covered by Unit 1's event model,
  extend it here rather than working around it with a guess.

**Manual verification:** flip DDRA bits and drive port output from the
VIA/emulator side; confirm the chevron direction and fill track reality.

---

## Unit 5 — Port A data-pin interactivity

**Depends on:** Unit 4.

**Scope:**
- Toggle click flips that pin's local-pull state and sends the
  corresponding `set_bits`/`reset_bits` call for its bit — mirroring
  `ButtonPeripheral.toggle`/`_send_bit`, but generalized to 8 independent
  bits on one port instead of one hardcoded bit.
- Momentary press asserts the *opposite* of the current toggle level for
  the duration of the press (per checkpoint 1's input-pin behavior:
  momentary overrides toggle-derived state while held), and releases back
  to the toggle's level on mouse-up.
- Reconnect must re-assert current local state for all 8 bits, same
  reasoning as `ButtonPeripheral.connect_if_needed`.
- LED now reflects the real, user-controlled local state instead of a
  fixed default.
- Enforce the "only touch configured bits" rule: this peripheral now owns
  all 8 bits of Port A's data lines by design (it's not sharing the port
  with another peripheral instance), so this is about correctness of the
  set/reset masks, not about restricting which bits get driven.

**Manual verification:** click each PA0–PA7 toggle and momentary; confirm
LED and VIA-side effect match; kill and restart the emulator/socket mid-
session and confirm state survives reconnect.

---

## Unit 6 — Port A control cells (CA1/CA2)

**Depends on:** Unit 5 (shares the row/cell architecture and reconnect
pattern).

**Scope:**
- `ControlCell` rendering: momentary-only (no toggle-as-pull), the
  pulse/level mode toggle + stylized 3-digit segment display (`PUL`/`LVL`)
  from checkpoint 2, and the polarity pulse-graph icon from checkpoint 1
  (rising = pulled-down/idle-low, falling = pulled-up/idle-high).
- Interactivity: momentary press in **level** mode asserts for as long as
  held (like a data pin's momentary); in **pulse** mode, a press fires one
  fixed-duration transition regardless of hold time. Polarity selects
  which direction that transition goes (matching the panel's designed use
  of testing edge-triggered IFR latching independent of human timing).
- Chevron stays the checkpoint-1 placeholder: always outlined, direction
  hardcoded per pin (CA1 = input, CA2 = output) rather than computed from
  live PCR state — computing it live from PCR is an explicitly deferred
  design item; don't attempt it here. Note in the PR description that
  this placeholder remains, so it's easy to find when PCR-driven direction
  is eventually tackled (Unit 10 is the natural point, since contention
  detection needs a real answer).
- LED: dark by default; per checkpoint 2's resolved semantics, it should
  show the pin's level *only when CA2 is currently serving as an
  output driven by the VIA*. If Unit 1's event model doesn't yet expose
  enough PCR state to determine "is CA2 currently an output," implement
  the always-dark placeholder (matching what `row_mockup.py` currently
  does) and flag the gap for Unit 10 rather than inventing a PCR read path
  ad hoc here.

**Manual verification:** exercise pulse and level modes with both
polarities on CA1 and CA2; confirm timing (pulse duration) and polarity
match expectations against known PCR handshake behavior.

---

## Unit 7 — Port B joins the panel; combined two-port window

**Depends on:** Unit 6.

**Scope:**
- Instantiate the Unit 3 row architecture a second time for Port B
  (PB0–PB5, CB1, CB2 — **not** PB6/PB7 yet, those are Units 8–9), reusing
  the same `Cell` classes and interactivity from Units 4–6 unchanged.
- Combine both ports into one window/canvas, mirroring the mockup's
  final two-port-at-scale layout: derive canvas width from actual laid-out
  content for both rows (not a guessed constant), matching checkpoint 2's
  fix for the margin/ordering bug in `row_mockup.py`.
- This is the point where duplicated per-port code would start to show if
  Unit 3's architecture wasn't actually parameterized — if you find
  yourself copy-pasting a per-port block here, that's a signal to go back
  and fix the Unit 3 abstraction rather than pushing forward.

**Manual verification:** both ports render side by side with symmetric
margins; interactivity on Port B (toggle/momentary/CB1/CB2) works
identically to Port A.

---

## Unit 8 — PB6 pulse-counting layered behavior

**Depends on:** Unit 7.

**Scope:**
- PB6 keeps full standard data-cell anatomy (LED, chevron, momentary) per
  the design doc's "layered capability, not a replacement" framing, plus
  the repurposed toggle → PUL/LVL mode-select + segment display from
  checkpoint 2 (same widget/position as the control cells' mode selector).
- Resolve, as a documented judgment call, the open question checkpoint 2
  flagged but didn't answer: whether the mode toggle is a manual
  panel-side override (the panel just fires momentary presses in pulse or
  level style, independent of actual VIA T2 configuration) or a live
  reflection of T2's actual pulse-counting-mode bit in ACR. The design
  doc's framing ("PB6 behaves like any other data pin except when T2's
  pulse-counting mode is active") suggests the panel should ideally know
  whether that mode is *actually* active and adjust behavior/labeling
  accordingly — if Unit 1's event model can expose the relevant ACR bit,
  prefer wiring it as a live indicator (manual toggle only chooses
  pulse-vs-level for the momentary's own behavior when the mode is
  active); otherwise, ship the manual-only version and note the gap.
- Also resolve the LED semantics fork checkpoint 2 flagged: PB6's `local`
  field means "forced pulled-up by configuration" rather than "toggle
  position" while pulse counting is active. Give this a distinct visual
  treatment (the checkpoint suggests this deserves "a shared solution"
  with the control-cell placeholder-chevron ambiguity — consider solving
  both here with one mechanism, e.g. a small fixed/placeholder marker
  convention reused in both places, rather than two bespoke fixes).

**Manual verification:** configure T2 for negative-edge pulse counting on
the emulator side; confirm PB6 forces pulled-up, the mode display and
momentary pulse/level behavior work, and the LED's fixed-vs-toggle
distinction is visually legible.

---

## Unit 9 — PB7 free-run indicator and audio output

**Depends on:** Unit 7 (can proceed in parallel with Unit 8 if reviewed
separately, since PB6 and PB7 don't share state).

**Scope:**
- PB7 keeps standard data-cell anatomy plus the speaker/audio-routing
  glyph from checkpoint 2 (bare polygon icon, no button chrome; on/off
  routing state is a panel-local setting, not VIA state; muted state is a
  single contrasting-color diagonal stroke, not a dim-on-dim one — the
  checkpoint notes this exact bug and how it was caught, don't reintroduce
  it).
- A small informational (non-fault) indicator showing when Timer 1's
  free-run/PB7-toggle mode (ACR bits 7:6 = `1x`) is currently driving PB7
  automatically — requires ACR readback via Unit 1's event model; extend
  it here if it doesn't yet cover ACR.
- Audio reconstruction: maintain a current-level flag for PB7 updated the
  instant a relevant Set/Reset message arrives (per the design doc, driven
  entirely by the message stream, not in-process timing since this
  peripheral is external to the emulator); feed an audio callback (e.g.
  `sounddevice`/PortAudio) from that flag to produce a naive,
  non-band-limited square wave. Start with the simple immediate-flip
  approach; don't attempt the jitter-mitigation "dedicated PB7 transport"
  extension described in the design doc unless the naive approach proves
  audibly broken — that's explicitly out of scope until then.
- Speaker icon toggles whether the audio callback is active; when T1 is
  driving PB7 automatically, the panel's own momentary/toggle for PB7
  should not fight it (PB7 is VIA-driven in this mode, same "pin can
  diverge from local" story as any output pin — no special-case wiring
  needed here beyond what output pins already do).

**Manual verification:** put T1 in free-run mode with a musical period,
confirm audible tone with routing on and silence with routing off; toggle
the T1-driving indicator on/off by leaving/entering free-run mode.

---

## Unit 10 — Contention detection and the aggregate Overload indicator

**Depends on:** Units 6, 8, 9 (needs direction/level answers from every
cell type, including the deferred PCR-driven control-line direction and
PB6/PB7 ACR-driven states).

**Scope:**
- Implement the design doc's `pin_driver_state(pin) -> { direction, level
  }` model as a real, single function consulted by every cell type
  (DDR for data pins, PCR for CA2/CB2, ACR for CB1/PB6/PB7 special
  cases, hardcoded for CA1/CB1-normally). This is the point where the
  placeholder control-line chevron direction (Unit 6) and PB6/PB7 ACR
  gaps (Units 8–9) should get resolved for real if they weren't already,
  since contention detection has no honest answer without them.
- Detect contention: panel toggle actively asserting one level while an
  output pin drives the opposite. Per the design doc, this is deliberately
  **not prevented** — it's flagged, not blocked.
- Single aggregate Short-Circuit/Overload indicator in the status bar:
  steady for one fault, a distinct blink pattern for multiple simultaneous
  faults; hover shows every currently-offending pin, not just the first.

**Manual verification:** deliberately configure a pin as VIA output while
holding the panel's toggle to the opposing level; confirm the indicator
lights, the blink pattern changes with a second simultaneous fault, and
the hover tooltip lists both.

---

## Unit 11 — Free/Guarded mode setting

**Depends on:** Unit 10.

**Scope:**
- Settings toggle (status bar `MODE: FREE`/`MODE: GUARDED` placeholder
  from Unit 3 becomes real) between:
  - **Free mode** (default): switches always live, contention flagged via
    the Unit 10 indicator only.
  - **Guarded mode**: switches auto-disable per `pin_driver_state`'s
    computed direction — e.g. a data pin currently driven as VIA output
    has its toggle/momentary rendered inert (visually distinct — dimmed or
    non-interactive) rather than able to create contention.
- This is additive over Unit 10's model; no new direction/level logic
  needed, just a gating behavior in the input-handling path.

**Manual verification:** switch to Guarded mode with a pin configured as
VIA output; confirm its switches stop responding and look visibly
disabled; switch back to Free and confirm they work again.

---

## Unit 12 — Switch bounce model

**Depends on:** Unit 11 (bounce applies to the same interactive paths;
easier to add once all switch types exist and behave correctly clean).

**Scope:**
- Per-switch-profile bounce (tactile pushbutton / toggle-rocker /
  worn-contact tiers — pick reasonable default intervals per tier and
  document them in the PR, since the design doc left exact defaults TBD).
- On actuation (press or release), schedule a Poisson-ish burst of
  transitions over `[0, T_bounce]`, settling cleanly at the intended level
  after; bounce must be injected into what's actually sent to the VIA
  (the true electrical signal), not just a decoration on a future trace
  view (Unit 13) — this ordering matters: get the "real" signal bouncing
  first, then Unit 13 will have real bounce data to draw.
- Bouncy pulse mode flag on control-line/PB6 pulse mode: bounce bursts on
  both the leading edge and the auto-released trailing edge.
- A per-switch bounce enable/disable independent of profile selection.

**Manual verification:** enable bounce on a pushbutton profile, drive it
against a VIA input with edge-sensitive firmware/test code, and confirm
multiple transitions actually arrive at the VIA per press (not just a
visual effect) — e.g. by watching an IFR-latching test case misbehave
correctly with bounce on and cleanly with it off.

---

## Unit 13 — Per-pin waveform trace

**Depends on:** Unit 12 (traces should show real bounce, per the design
doc's "reveals what's really hitting the wire" intent, so bounce should
already be real by the time this renders it).

**Scope:**
- Fixed-capacity ring buffer of `(timestamp, level)` transition pairs per
  pin (not per-sample) — bounded memory even at high toggle rates.
- Records the true electrical level (post-bounce), not the debounced
  intent.
- Rendered as a step waveform; decide on presentation (a toggleable
  per-cell mini-trace vs. a dedicated trace panel/view) as part of this
  unit's scope and document the choice — the design doc mentions the
  `crossbeam-channel`-style overflow-policy pattern used elsewhere in the
  project as prior art for the buffer's overflow behavior, worth reusing
  the same policy rather than inventing a new one.

**Manual verification:** trigger bounce on a switch and confirm the trace
visibly shows the bounce burst, not a single clean edge.

---

## Unit 14 — Presets and snapshots

**Depends on:** Unit 11 (snapshots capture control state, which includes
the Free/Guarded setting and per-pin control configuration established by
then; doesn't need bounce/trace).

**Scope:**
- **Quick actions** (no naming, always available): all pins high, all
  pins low, release all momentaries (kept distinct from toggle/level
  reset, since momentary and toggle/level state are separate axes per the
  design doc).
- **Named snapshots**: serialize panel *control* state only (toggle
  levels, control-pin polarity selections, pulse/level/bouncy-mode flags,
  per-switch bounce overrides) — explicitly not pin electrical levels,
  since level is a downstream consequence of control state plus live VIA
  behavior (the design doc is explicit that forcing levels directly would
  reintroduce the contention questions Units 10–11 already solved).
- Flat JSON, versioned schema, strict parsing that fails hard on
  unrecognized/malformed fields (matching the project's existing
  VICE-label-file-parser convention mentioned in the design doc — check
  that parser for the house style before writing this one).

**Manual verification:** save a snapshot with several non-default control
settings, reset to defaults, reload the snapshot, confirm every control
setting (not pin level) is restored exactly; confirm a hand-edited
malformed snapshot file fails to load with a clear error rather than
partially applying.

---

## Unit 15 — Cleanup pass on accumulated open concerns

**Depends on:** all prior units.

**Scope:** By this point several deliberately-deferred items have had a
chance to surface real answers. Sweep them:

- Minimum tappable/clickable size for toggle and momentary controls at the
  current narrow cell width (flagged in both checkpoints, never
  evaluated) — measure against actual usage from Units 5–9 and adjust if
  it's genuinely been awkward.
- Whether cell-level contention (a genuine short, as opposed to the
  ordinary pull-up-loses-to-output case) deserves its own visual cue
  beyond the aggregate Overload indicator — revisit now that Unit 10 has
  been lived with.
- Confirm the control-cell placeholder-chevron and PB6 fixed-vs-toggle LED
  ambiguities (Units 6 and 8) ended up with the "shared solution" the
  design docs asked for, rather than two independent patches that happen
  to look different.
- Confirm the arbitrary on/off conventions called out in checkpoint 2
  (toggle-on-means-pulse, speaker-on-means-routed) still feel right now
  that they're live and driven by real VIA state, not just a static mock.
- Any other item still listed under "Open questions" in either checkpoint
  that a prior unit's notes above didn't explicitly claim.

This unit is deliberately not itself a source of new features — if a
"cleanup" turns into a redesign, split it out and get sign-off before
proceeding, rather than folding a big change into what should be a small
PR.

**Manual verification:** run through both checkpoints' "Open questions"
sections and confirm each item is either resolved (note how, briefly, in
the PR) or explicitly still open with a one-line reason why.
