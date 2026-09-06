# UAT: Unit 6 -- Port A control cells (CA1/CA2)

Throwaway verification material for Unit 6
(`via-playground/src/emma65_via_playground/app.py`'s `ControlPinState`,
`Peripheral.press_ctrl`/`release_ctrl`/`update_ctrl_pulses`/
`toggle_ctrl_mode`/`toggle_ctrl_polarity`, and `cells.ControlCell`'s
`mode_rect`/`polarity_rect`/`momentary_rect` hit-testing).

This unit makes CA1/CA2's mode toggle, polarity icon, and momentary button
actually drive the VIA's control-pin lines (`SCA1`/`RCA1`/`SCA2`/`RCA2`).
The 6502 program here leaves PCR at its power-on default (`$00`), which
makes both CA1 and CA2 negative-edge-sensitive interrupt inputs, and prints
`IFR & $03` (bit 1 = CA1, bit 0 = CA2) as two hex digits plus CRLF to the
emulator's `console` device every time either flag latches, immediately
clearing whichever bits it just printed.

With PCR fixed to negative-edge detection, only a high-to-low transition
sets a flag. A full momentary interaction (press + release, or a pulse
mode's auto-revert) always contains exactly one high-to-low edge regardless
of which polarity you've selected:

- **Rising polarity** (idle low, active high): the *release* (or the
  pulse's automatic revert-to-idle) is the high-to-low edge that gets
  caught and printed.
- **Falling polarity** (idle high, active low): the *press* itself is the
  high-to-low edge that gets caught and printed.

So every interaction should produce exactly one `01` (CA1), `02` (CA2), or
occasionally `03` (both, if you click both at once) printed to the console
-- which edge of your click produced it tells you whether polarity is
behaving as expected.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-6-port-a-control-cells
ca65 -g --cpu w65c02 unit6_uat.s -o unit6_uat.o
ld65 --config unit6_uat.cfg unit6_uat.o -o unit6_uat.bin
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
terminal into raw mode; you won't see any output until the first CA1/CA2
edge is caught (unlike Units 4/5, this program doesn't print anything at
startup).

## Run the peripheral and check the window

In another terminal, from the `emma65-peripherals` repo root:

```bash
uv run --package emma65-via-playground emma65-via-playground
```

Only CA1/CA2 are in scope for this unit; Port A's data pins (PA0-PA7) work
exactly as they did in Unit 5 and aren't the focus here.

Check, for **both CA1 and CA2**:

1. **Mode toggle:** click the toggle switch above the segment display. It
   should flip between `LVL` and `PLS`, and the toggle itself should
   visually flip on/off in sync (on = pulse).
2. **Level mode, rising polarity (the default):** with the mode toggle off
   (`LVL`) and the polarity icon showing rising (bold blue rising edge),
   press and hold the momentary button. Nothing should print yet. Release
   it -- the console should immediately print `01` for CA1 or `02` for
   CA2. Holding longer before releasing shouldn't change anything other
   than delaying that print.
3. **Level mode, falling polarity:** click the polarity icon to flip it to
   falling (bold orange falling edge). Press the momentary -- the console
   should print immediately on **press** this time, not on release.
   Releasing afterward should print nothing further.
4. **Pulse mode, either polarity:** flip the mode toggle to `PLS`. Click
   (a quick press+release, or press-and-hold well past a second) the
   momentary once. The console should print once, roughly 100ms after the
   press (not tied to when you release the mouse button) -- confirm this
   by holding the button down for a couple of seconds and observing the
   print happens quickly, well before you release.
5. **Only the clicked pin's control line moves:** clicking CA1's controls
   must never print `02` (or affect CA2's mode/polarity display), and vice
   versa.
6. **Chevron and LED stay placeholders:** neither CA1 nor CA2's chevron or
   LED should change appearance during any of the above -- both are
   documented placeholders until Unit 10 (chevron: always outlined,
   hardcoded direction; LED: always dark).
7. **Reconnect re-assertion:** set CA1 or CA2 to a non-default mode or
   polarity (or leave a level-mode momentary held down), then kill and
   restart `emma65` mid-session. The connection status line should flip to
   `connecting...` and back to `connected`; the mode/polarity display
   should be unchanged throughout (they never depended on the connection),
   and if a level-mode momentary was held through the drop, releasing it
   after reconnect should still print the expected edge.
