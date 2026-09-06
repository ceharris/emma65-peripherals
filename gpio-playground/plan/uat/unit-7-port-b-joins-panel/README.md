# UAT: Unit 7 -- Port B joins the panel; combined two-port window

Throwaway verification material for Unit 7
(`via-playground/src/emma65_via_playground/cells.py`'s `build_port`/
`build_port_b`/`layout_ports`, and `app.py`'s `PortIO`-backed `Peripheral`
now driving both Port A and Port B).

This unit brings Port B (PB0-PB5, CB1, CB2 -- **not** PB6/PB7 yet) into the
same window as Port A, side by side, with symmetric margins. Interactivity
on Port B (toggle, momentary, control-pin mode/polarity/momentary) should
work identically to Port A, which already went through Units 4-6's UAT.

## Run the peripheral with all-input direction masks

This ROM declares **DDRA=$00 and DDRB=$00 -- every PAx/PBx bit is a VIA
input**, deliberately sidestepping VIA-output/contention scenarios (that's
Unit 10's territory, and also the subject of
[ceharris/emma65-rust#609](https://github.com/ceharris/emma65-rust/issues/609):
emma65's `PortState` broadcast doesn't yet compose DDR correctly when a
peripheral, rather than the 6502 program, changes port data, so a VIA-output
pin's chevron currently follows the panel's own click instead of staying
locked to what the VIA is actually driving). Match the peripheral's declared
direction to the ROM's real one so the chevron arrows are accurate too:

```bash
uv run --package emma65-via-playground emma65-via-playground --pa-direction 00 --pb-direction 00
```

## What the ROM does

Leaves PCR at its power-on default (`$00`), which makes CA1/CA2/CB1/CB2 all
negative-edge-sensitive interrupt inputs (same as Unit 6, just now covering
both ports' control pins). It prints to the emulator's `console` device
whenever:

- `Cxx` -- a genuine CA1/CA2/CB1/CB2 edge (bit0=CA2, bit1=CA1, bit3=CB2,
  bit4=CB1)
- `Axx` -- Port A's live level (ORA) changed to `xx`
- `Bxx` -- Port B's live level (ORB) changed to `xx`

Getting a clean `Cxx` signal took two fixes, both confirmed by reading
emma65's actual `via6522.rs` rather than assuming datasheet behavior --
worth knowing if this ever needs touching again:

1. **IFR must be read before ORA/ORB, every iteration.** Reading `ORA`
   always clears CA1's flag, and clears CA2's too since PCR's
   independent-mode bit is 0 (dependent mode); `ORB` does the same for
   CB1/CB2. Read them in the wrong order and a control-pin edge gets
   silently wiped before this program ever sees it -- symptom was clicking
   CB1/CB2 repeatedly with no `Cxx` printed at all.
2. **CA1/CB1 also fire on ordinary data-pin writes, and that's intentional
   on emma65's side.** `plan/6522-via-edge-cases.md` in the emma65 repo
   documents that *any* Port A data change sets IRQ_CA1 (and Port B sets
   IRQ_CB1) -- "data + strobe bundled in one message" for virtual
   peripherals. That means clicking an ordinary PAx/PBx toggle also flags
   CA1/CB1, with nothing to do with the actual CA1/CB1 control lines --
   symptom was `Cxx` appearing (or CA1/CB1 checks looking unreliable) while
   just clicking data toggles. This ROM filters it: a genuine CA1/CB1 edge
   (its own `SC`/`RC` message) never coincides with an ORA/ORB change in
   the same poll iteration, so if `ORA` changed this iteration, that
   iteration's CA1 bit is presumed to be the data write's side effect and
   isn't printed (same for `ORB`/CB1). **This is why DDRA/DDRB must stay
   `$00` for this filter to work** -- a bit declared a VIA *output* would
   still flip IRQ_CA1/CB1 on a panel click without ever showing up in
   ORA/ORB (DDR masks it out of the read), which would defeat the filter.

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

## Check the window

Launch the peripheral as shown above (with `--pa-direction 00
--pb-direction 00`).

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

4. **Every PB0-PB5 toggle/momentary**: click each toggle -- the LED should
   light, and the console should print `Bxx` with the corresponding bit
   set. Press-and-hold the momentary -- console prints the *opposite*
   level momentarily (LED dims/lights to match), then prints back to the
   toggle's level on release. The chevron should track the same `Bxx`
   value the console prints, since every bit is a VIA input here (the
   panel is the only driver, no contention to worry about for this UAT).
5. **CB1/CB2 mode toggle, polarity, momentary**: repeat Unit 6's checks
   (level-mode press-then-release prints on release for rising polarity,
   press for falling polarity; pulse mode prints once ~100ms after press
   regardless of hold time) and confirm you see `C08` (CB2) or `C10` (CB1)
   at the right moment -- and confirm ordinary PB toggle clicks in between
   *don't* also produce a `Cxx` line. Confirm clicking CB1's controls never
   produces a CB2 print and vice versa.
6. **Chevron and LED stay placeholders for CB1/CB2**: same as CA1/CA2 --
   always-outlined chevron, always-dark LED.

### Cross-port isolation

7. **Interacting with Port A never affects Port B's display or console
   output, and vice versa** -- e.g. toggling PA1 should never print a `Bxx`
   line, and pressing CB1 should never print `C02` (CA2) or `C01` (CA1).

### Reconnect

8. Set some Port A *and* Port B state (a toggle, a control-pin mode/
   polarity, a held level-mode momentary) then kill and restart `emma65`
   mid-session. The connection status line should flip to `connecting...`
   and back to `connected`; all of that state (both ports) should be
   unchanged throughout, and re-assertion should bring the emulator's view
   back in sync with what's on screen for both ports.
