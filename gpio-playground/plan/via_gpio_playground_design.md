# VIA GPIO Playground — Design Checkpoint

A design summary for a virtual GPIO panel peripheral for `emma65`'s 6522 VIA
emulation. The panel connects over the existing VIA peripheral wire protocol
(ASCII/binary) and gives a human observer/manipulator access to every pin on
Port A and Port B, in the spirit of a physical LED-and-switch breadboard
bring-up panel. It is implemented as a standalone peripheral (likely Python,
e.g. Pygame), external to the emulator/debugger process, and connects over a
UNIX domain socket — intentionally simple and easy for others to fork and
extend.

## Scope

- Port A: 8 data pins (PA0–PA7) + CA1 + CA2
- Port B: 8 data pins (PB0–PB7) + CB1 + CB2
- Every pin is independently observable (LED) and manipulable (switches) as
  needed for its role.

## Per-pin cell — standard data pins (PA0–PA7, PB0–PB7 except PB6/PB7 specifics below)

Each cell models a small virtual circuit:

- Pull-up resistor to VCC on the shared node.
- The node is the pin as seen by the VIA (both directions share one node).
- Two parallel paths to ground: a **momentary switch** and a **toggle
  switch**, giving two independent ways to pull the line low.
- A **state LED** on the same node, reflecting the current logic level
  regardless of which side (panel or VIA) is currently driving it.

### PB6 — special case

PB6 is a standard bidirectional data cell (toggle + momentary + LED) **and**
additionally supports **pulse mode** on its momentary switch, because PB6 is
the external pulse-counting input for Timer 2 (ACR bit 5). Pulse mode is a
layered capability on top of the standard cell, not a replacement — PB6
behaves like any other data pin except when T2's pulse-counting mode is
active.

### PB7 — special case

PB7 is a standard bidirectional data cell, with an additional note: when
Timer 1 is in free-run/PB7-toggle mode (ACR bits 7:6 = `1x`), the VIA toggles
PB7 automatically to produce a square wave (classic period technique for
simple tone generation). See **Audio output** below. A small informational
indicator on the panel (not a fault indicator) can show when T1 is currently
driving PB7 in this mode, since PB7's cell is otherwise just an ordinary data
pin.

## Per-pin cell — control lines (CA1, CA2, CB1, CB2)

Control lines differ enough from data pins to warrant a distinct cell design:

- **Momentary switch only** — no toggle, since these are edge/handshake
  signals rather than steady-state data lines.
- **Pulse vs. level mode**, selectable per switch:
  - *Level*: pin tracks the button for as long as it's held.
  - *Pulse*: a press fires one fixed-duration transition regardless of hold
    time — suited to testing edge-triggered IFR latching without depending
    on human timing.
- **Pull-up/pull-down polarity toggle** — lets a single momentary switch
  generate either a rising-edge or falling-edge transition, matching the
  active-edge polarity selectable via CRA/CRB.
- **Optional "bouncy" pulse mode** — see Switch bounce model below. This is a
  flag on top of pulse mode (not a third mode), and produces bounce bursts
  on *both* the leading and trailing (auto-released) edges, since real
  contacts bounce on release too.

## Direction / driver-state model

Direction for a given pin is **not** uniformly governed by DDR:

- Data pins (PA0–PA7, PB0–PB5): direction from DDRA/DDRB.
- CA1: always an input.
- CA2, CB2: direction depends on PCR mode bits (handshake / pulse / manual
  output vs. input modes).
- CB1: normally an input, but becomes an output (shift clock) in certain ACR
  shift-register modes.
- PB6: normal DDR-governed data pin, *except* it's also T2's external
  pulse-counting input — a driver-state consideration independent of DDRB6.
- PB7: normal DDR-governed data pin, *except* T1's free-run mode can drive it
  directly regardless of DDRB7.

Design conclusion: implement a single `pin_driver_state(pin) -> { direction,
level }` function per pin, where each pin type consults whichever of
DDR/PCR/ACR is authoritative for it. Data pins and control pins have
genuinely different direction-determination logic even though they feed the
same downstream contention check.

## Misconfiguration handling

Rather than preventing misconfiguration (e.g. auto-disabling switches based
on computed direction), the panel **allows contention** as an educational
feature:

- A single aggregate **Short-Circuit/Overload indicator** on the panel.
  - Steady light = one fault; distinct blink pattern = multiple simultaneous
    faults.
  - Hovering shows an explanation enumerating *every* currently-offending
    pin, not just the first found.
- A settings toggle between:
  - **Free mode** (default) — switches always live, contention flagged via
    the indicator. The primary educational experience.
  - **Guarded mode** — switches auto-disable per computed direction, for
    when someone just wants clean I/O without further exploration.

## Per-pin waveform trace

Each pin maintains a small trace, analogous to a logic analyzer channel:

- Implemented as a fixed-capacity ring buffer of `(timestamp, level)`
  transition pairs (not per-sample), keeping memory bounded even at high
  toggle rates.
- Likely reuses the `crossbeam-channel` + overflow-policy pattern already
  used for CPU trace offloading.
- Records the pin's **true electrical level** (post-bounce, what the VIA
  actually sees), not the debounced/intended level — the point is to reveal
  what's really hitting the wire.
- Rendered as a step waveform by walking the transition list.

## Switch bounce model

- Bounce is modeled **per switch type/profile**, not as a raw millisecond
  value the user has to tune. Reasonable defaults are consistent across all
  switches of a given profile; users only override where it matters.
  - Example profile tiers: small tactile pushbutton (short interval),
    toggle/rocker switch (medium), worn/high-mileage contact (long) — exact
    defaults TBD.
- On actuation (press or release), a burst of random transitions is
  scheduled over the profile's bounce interval `[0, T_bounce]`, using a
  Poisson-ish process (matches real contact bounce better than a fixed
  pattern). After `T_bounce`, the pin is forced to settle cleanly at the
  intended level.
- Bounce injection happens at the level of what's actually sent to the VIA
  (the true electrical signal), not just as decoration on the displayed
  trace — otherwise firmware being tested never actually sees the noise.
- **Bouncy pulse mode** (control lines, PB6): an opt-in flag on pulse mode
  that replaces the idealized clean edge with a full bounce burst around
  *both* the leading and the auto-released trailing edge, still governed by
  the switch's profile. Plain pulse mode remains the clean/idealized
  default.
- A per-switch bounce enable/disable is available independent of profile
  selection, for isolating other behavior under test.

## Presets and reset

Two tiers:

- **Quick actions** (always available, no naming required):
  - All pins high
  - All pins low
  - Release all momentaries (distinct from toggle/level reset, since
    momentary and toggle/level state are separate axes)
- **Named snapshots** — full serialized capture and reload of panel *control
  state* (not pin electrical state):
  - Toggle levels, pull-up/pull-down polarity selection per control pin,
    pulse/level/bouncy-mode flags, and any per-switch bounce profile
    overrides.
  - Stored as flat JSON with a versioned schema; strict parsing that fails
    hard on unrecognized/malformed fields rather than silently partial-
    loading (consistent with existing project conventions, e.g. the VICE
    label file parser).
  - Snapshots deliberately do not attempt to capture pin *levels* directly,
    since level is a downstream consequence of control state plus whatever
    the VIA is doing at load time — forcing levels directly would
    reintroduce the contention questions solved above.

## Audio output (PB7)

- The panel peripheral is external to the emulator/debugger, connected only
  over the socket — so PB7 audio reconstruction is driven entirely by the
  Set/Reset message byte stream for that pin, not by in-process timing.
- Reconstruction approach: a shared current-level state, flipped the instant
  a relevant Set/Reset message for PB7 arrives; an audio output callback
  (e.g. via `sounddevice`/PortAudio) fills each sample block from the
  current level — no synthesis math needed since it's already a literal
  square wave.
- Naive square-wave output (no band-limiting) is considered acceptable and
  arguably more period-correct than smoothing, since it matches what the
  real hardware actually produced.
- Known risk: jitter/coalescing from socket delivery timing, GC pauses, OS
  scheduling, etc. Decision: start with the naive immediate-flip approach
  and only address jitter if it proves to be an actual audible problem.
- **Future extension, if jitter becomes a real issue**: a dedicated,
  point-to-point, unidirectional transport purpose-built for delivering
  timestamped PB7 edges, separate from the general multi-peripheral VIA
  transport.
  - Minimal fixed-width `(timestamp, level)` wire format; no message-type
    discrimination needed since it only ever carries one kind of record.
  - Timestamp domain: leaning toward VIA cycle count (decouples the edge
    record from wall-clock scheduling; Python side converts using the
    emulator's configured clock rate) over host monotonic time.
  - Benefit beyond jitter: fixes edge *coalescing* (two edges arriving
    between audio-callback samples losing a transition entirely), since the
    receiver can reconstruct the correct level at any sample instant from
    the timestamped edge history rather than only ever knowing the "current"
    state.
  - Would be documented as an additive extension to the existing wire
    protocol spec (e.g. a new message type or a separate mini-protocol
    section) rather than a redesign of it.

## Open / deferred items

- Exact default bounce intervals per switch profile.
- Panel-level layout (arrangement of the 20 cells, DDR/direction indicators,
  overload indicator placement).
- Socket client implementation details for the panel peripheral itself.
- JSON snapshot schema (field names, versioning scheme).
- Whether/how the informational "T1 driving PB7" indicator is presented
  alongside the standard PB7 cell.
