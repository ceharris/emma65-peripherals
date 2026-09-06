# UAT: Unit 7 -- Port B joins the panel; combined two-port window

Throwaway verification material for Unit 7
(`via-playground/src/emma65_via_playground/cells.py`'s `build_port`/
`build_port_b`/`layout_ports`, and `app.py`'s `PortIO`-backed `Peripheral`
now driving both Port A and Port B).

This unit brings Port B (PB0-PB5, CB1, CB2 -- **not** PB6/PB7 yet) into the
same window as Port A, side by side, with symmetric margins. Interactivity
on Port B (toggle, momentary, control-pin mode/polarity/momentary) should
work identically to Port A, which already went through Units 4-6's UAT.

The 6502 program here configures DDRA/DDRB to match the panel's own
`--pa-direction`/`--pb-direction` defaults (`$F0`, `$38`), so PA3-PA0 and
PB2-PB0 are VIA inputs -- the panel's toggle/momentary drive them directly,
with no contention -- while PA7-PA4 and PB5-PB3 stay VIA-driven outputs this
program never touches. It leaves PCR at its power-on default (`$00`), which
makes CA1/CA2/CB1/CB2 all negative-edge-sensitive interrupt inputs (same as
Unit 6, just now covering both ports' control pins). It prints to the
emulator's `console` device whenever:

- `Cxx` -- `IFR & $1B` just went nonzero (bit0=CA2, bit1=CA1, bit3=CB2,
  bit4=CB1), immediately cleared after printing
- `Axx` -- Port A's live level (ORA) changed to `xx`
- `Bxx` -- Port B's live level (ORB) changed to `xx`

**IFR is checked before ORA/ORB on every poll iteration, and that order
matters**: with PCR left at `$00`, CA1/CB1's flags are unconditionally
cleared by any ORA/ORB access, and CA2/CB2's are cleared too since PCR's
independent-mode bits are also 0. An earlier version of this ROM read
ORA/ORB first, which silently wiped control-pin edges before the code ever
checked for them -- symptom was clicking CB1/CB2 repeatedly with no `Cxx`
printed. If you see that symptom again, suspect this ordering first.

**PA7-PA4 and PB5-PB3 are declared VIA outputs and this ROM never drives
them, so they read back low regardless of the panel's toggle -- that's
expected contention (the panel's pull loses to the VIA's inactive-but-still-
driving output), not a bug. Use PA3-PA0 and PB2-PB0 to confirm toggle/
momentary correctness on data pins.**

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-7-port-b-joins-panel
ca65 -g --cpu w65c02 unit7_uat.s -o unit7_uat.o
ld65 --config unit7_uat.cfg unit7_uat.o -o unit7_uat.bin
```

## Run the emulator

There is no `emma65` on `$PATH` by default -- build one from current
`emma65-rust` source:

```bash
cd path/to/emma65-rust   # the emma65 (Rust) checkout, not this repo
cargo build
target/debug/emma65 --config path/to/emulator.toml
```

Run this **in a real terminal, not redirected/piped** -- the `console`
device attaches to this process's own stdin/stdout by default and puts the
terminal into raw mode; you won't see any output until the first tracked
change.

## Run the peripheral and check the window

In another terminal, from the `emma65-peripherals` repo root:

```bash
uv run --package emma65-via-playground emma65-via-playground
```

### Layout

1. **Both ports render side by side** in one window: Port A's row (PA7...PA0,
   CA1, CA2) on the left, Port B's row (PB5...PB0, CB1, CB2) on the right,
   with a visibly larger gap between CA2 and PB5 than between adjacent cells
   within a port.
2. **Symmetric margins**: the left edge of PA7's cell and the right edge of
   the window (minus CB2's cell) should look like mirror-image margins --
   there shouldn't be noticeably more empty space on one side than the
   other.
3. **Status bar** reads a combined title (not just "PORT A").

### Port B interactivity (should match Port A's Unit 5/6 behavior exactly)

4. **PB0-PB2 toggle/momentary**: click each toggle -- the LED should light,
   and the console should print `Bxx` with the corresponding bit set.
   Press-and-hold the momentary -- console prints the *opposite* level
   momentarily, then prints back to the toggle's level on release.
5. **PB3-PB5 toggle/momentary**: clicking these still flips the LED/toggle
   locally (panel-side state), but since this ROM declares them VIA outputs
   without driving them, `Bxx` will keep reading with those bits low
   regardless -- this is the expected contention case described above, not
   a failure.
6. **CB1/CB2 mode toggle, polarity, momentary**: repeat Unit 6's checks
   (level-mode press-then-release prints on release for rising polarity,
   press for falling polarity; pulse mode prints once ~100ms after press
   regardless of hold time) and confirm you see `C08` (CB2) or `C10` (CB1)
   at the right moment. Confirm clicking CB1's controls never produces a
   CB2 print and vice versa.
7. **Chevron and LED stay placeholders for CB1/CB2**: same as CA1/CA2 --
   always-outlined chevron, always-dark LED.

### Cross-port isolation

8. **Interacting with Port A never affects Port B's display or console
   output, and vice versa** -- e.g. toggling PA1 should never print a `Bxx`
   line, and pressing CB1 should never print `C02` (CA2) or `C01` (CA1).

### Reconnect

9. Set some Port A *and* Port B state (a toggle, a control-pin mode/
   polarity, a held level-mode momentary) then kill and restart `emma65`
   mid-session. The connection status line should flip to `connecting...`
   and back to `connected`; all of that state (both ports) should be
   unchanged throughout, and re-assertion should bring the emulator's view
   back in sync with what's on screen for both ports.
