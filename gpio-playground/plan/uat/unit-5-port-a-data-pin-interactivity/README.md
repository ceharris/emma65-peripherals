# UAT: Unit 5 -- Port A data-pin interactivity

Throwaway verification material for Unit 5
(`via-playground/src/emma65_via_playground/app.py`'s `Peripheral.toggle_pa`/
`set_pa_momentary` and the run loop's toggle/momentary click handling).

This unit makes PA0-PA7's toggle and momentary widgets actually drive the
VIA. The 6502 program here sets DDRA to `$00` -- every Port A data pin is a
VIA *input* -- so the panel is the sole driver of all 8 lines, and prints
ORA as two hex digits (plus CRLF) to the emulator's `console` device every
time it changes, so you can watch what actually arrives at the VIA
independent of the pygame window.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-5-port-a-data-pin-interactivity
ca65 -g --cpu w65c02 unit5_uat.s -o unit5_uat.o
ld65 --config unit5_uat.cfg unit5_uat.o -o unit5_uat.bin
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
terminal into raw mode; you should see `00` print immediately on launch
(Port A's initial level, before anything's clicked).

## Run the peripheral and check the window

In another terminal, from the `emma65-peripherals` repo root, using
`--pa-direction 00` so the panel draws PA0-PA7 as inputs, matching the
program's actual DDRA:

```bash
uv run --package emma65-via-playground emma65-via-playground --pa-direction 00
```

Check:

1. **Toggle click:** click each PA0-PA7 toggle. Its LED should light/dark
   immediately with the toggle position, and its chevron should fill/empty
   to match shortly after (the chevron follows the VIA's echoed pin-level
   event, not the click directly). The emulator terminal should print the
   new ORA value in hex, matching the bits you've toggled on.
2. **Momentary press (toggle off):** press and hold a PA pin's momentary
   button while its toggle is off. The chevron should fill for as long as
   held (asserting the opposite of the toggle's low level) and the console
   should print the level with that bit set; releasing should print the
   level with that bit clear again. The LED and toggle switch should *not*
   move -- they reflect the toggle position, not the momentary override.
3. **Momentary press (toggle on):** toggle a pin on (LED lit), then press
   its momentary. The chevron should empty (momentary overrides to the
   opposite, i.e. low) while held, and refill when released. Again, the LED
   stays lit throughout -- only the chevron and the console output should
   move.
4. **Only the clicked pin changes:** clicking one pin's toggle/momentary
   must never move another pin's LED, toggle, or chevron.
5. **Reconnect re-assertion:** with a few toggles set to non-default
   positions (and no momentary held), kill and restart `emma65` mid-session.
   The connection status line should flip to `connecting...` and back to
   `connected`; once reconnected, the console should reprint the same ORA
   value the panel had before the drop (all 8 bits re-sent), and the panel's
   LEDs/toggles should be unchanged throughout (they never depended on the
   connection).
