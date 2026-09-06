# UAT: Unit 4 -- live pin-state for Port A data pins

Throwaway verification material for Unit 4
(`via-playground/src/emma65_via_playground/app.py`'s `Peripheral._handle_event`
and the per-frame chevron-fill update in `run()`).

This unit wires the PA0-PA7 chevron *fill* to real VIA port-state traffic.
Chevron *direction* (shape/color) is **not** derived from anything live --
the VIA peer protocol never conveys DDR, so direction is a declared
`--pa-direction` setting the panel operator sets to match their ROM. The
6502 program here deliberately changes DDRA partway through to demonstrate
that fill keeps tracking reality even when the panel's declared direction
no longer matches it -- and repeats that cycle forever (~8s per full
cycle), so there's no race between starting the emulator and starting the
peripheral to catch the upper-nibble phase.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-4-port-a-live-pin-state
ca65 -g --cpu w65c02 unit4_uat.s -o unit4_uat.o
ld65 --config unit4_uat.cfg unit4_uat.o -o unit4_uat.bin
```

## Run the emulator

There is no `emma65` on `$PATH` by default -- build one from current
`emma65-rust` source:

```bash
cd path/to/emma65-rust   # the emma65 (Rust) checkout, not this repo
cargo build
target/debug/emma65 --config path/to/emulator.toml
```

## Run the peripheral and check the window

In another terminal, from the `emma65-peripherals` repo root, using the
default `--pa-direction` (`F0`, matching the program's initial DDRA):

```bash
uv run --package emma65-via-playground emma65-via-playground
```

Check (the whole cycle below repeats forever, ~8s per cycle, so you don't
need to catch it at any particular moment -- just watch for a few cycles):

1. **~4 seconds with DDRA = $F0 (PA7-4 out):** the program walks a single
   bit through PA7-4 (`$10 -> $20 -> $40 -> $80`, ~1s per step, then wraps
   and repeats 4 times). Confirm PA7-PA4 (chevrons apex-down/orange,
   declared "out") light up filled one at a time in that order, while
   PA3-PA0 (apex-up/blue, declared "in") stay outlined/dark throughout --
   nothing drives them yet.
2. **Then ~4 seconds with DDRA = $0F (PA3-0 out):** the program switches to
   walking a bit through PA3-0 (`$01 -> $02 -> $04 -> $08`, then wraps, 4
   times). The panel is still using `--pa-direction F0`, so it still draws
   PA3-PA0 as inputs (apex-up/blue) -- but their chevron *fill* should
   still light up one at a time in step with the program, proving fill
   tracks the live VIA state regardless of the panel's declared direction.
   PA7-4 (still drawn as outputs) should go/stay dark, since they're now
   real VIA inputs with nothing external driving them.
3. The program then jumps back to step 1 and repeats indefinitely.
4. Kill and restart `emma65` mid-run (as in prior units): the connection
   status line should flip to `connecting...` and back to `connected`
   within about a second, and pin walking should resume tracking correctly
   once reconnected (the panel doesn't need to be restarted).

Optionally, re-run with a `--pa-direction` that matches the *second* half of
the program instead (`--pa-direction 0F`) to see PA3-PA0 correctly drawn as
outputs and PA7-PA4 as inputs -- confirming the flag actually changes the
declared direction shown, independent of fill behavior.
