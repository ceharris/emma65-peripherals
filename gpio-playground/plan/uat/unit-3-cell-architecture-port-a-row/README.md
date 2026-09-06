# UAT: Unit 3 -- reusable cell-rendering architecture + static Port A row

Throwaway verification material for Unit 3. This unit translates the settled
visual design (checkpoints 1 & 2) into the `Cell`/`DataCell`/`ControlCell`
class hierarchy (`via-playground/src/emma65_via_playground/cells.py`) and
renders a static placeholder Port A row -- no live VIA pin traffic and no
interactivity yet, so the 6502 program here does nothing but keep the CPU
running while the `via/6522` device's socket stays up, same as Unit 2.

The row-layout math (cell placement, the `ctrl_group_gap` spacing cue,
symmetric canvas margins) is unit-tested
(`via-playground/tests/test_cells.py`). What's left to check by hand is
whether pygame actually draws the right pixels, and that the connection
status footer text still tracks the socket going up/down as it did in
Unit 2.

`port_a_reference.png` alongside this file is a headless self-rendered
capture of the current code (same window size, same drawing calls the
running peripheral uses) -- use it as the fidelity reference instead of
`row_mockup.png`, which depicts Port B's later, PB6/PB7-specific layout.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-3-cell-architecture-port-a-row
ca65 -g --cpu w65c02 unit3_uat.s -o unit3_uat.o
ld65 --config unit3_uat.cfg unit3_uat.o -o unit3_uat.bin
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

In another terminal, from the `emma65-peripherals` repo root:

```bash
uv run --package emma65-via-playground emma65-via-playground
```

Check, comparing against `port_a_reference.png`:

1. A window opens sized to fit the status bar plus a ten-cell Port A row
   (roughly 652x460).
2. Status bar chrome: a dim "OVERLOAD" LED + label on the left, "PORT A"
   centered as the title, "MODE: FREE" in gold and the "emma65" wordmark on
   the right.
3. Ten cells left to right: `PA7`..`PA0` (data cells), then a visible gap,
   then `CA1`/`CA2` (control cells).
   - Each cell has a label above a chevron (triangle) above a rounded
     panel body.
   - Data-cell chevrons: apex-up/blue = input (PA2, PA1, PA0), apex-down/
     orange = output (PA7-PA3); filled = pin high, outline = pin low --
     compare fill against `port_a_reference.png` pin-by-pin.
   - Data-cell body: LED (green when local is high, dark otherwise) above
     a toggle (green/right when local is high) above a momentary button
     (only PA1's should show the pressed glow).
   - Control-cell chevrons (CA1, CA2) are always outlined, never filled.
   - Control-cell body: a dark LED (always off), a mode toggle, a `PUL`/
     `LVL` amber segment readout below it (CA1 = `PUL`, CA2 = `LVL`), and a
     small pulse-polarity icon (blue rising edge for CA1, orange falling
     edge for CA2).
4. Below the row, a connection-status line reading
   `connected  (~/.emma/sock/via6522)` in green.
5. Kill the `emma65` process (Ctrl-C in its terminal). Within about a
   second the status line should flip to `connecting...` in red; the Port A
   row keeps rendering unchanged (it's static placeholder state, not driven
   by the connection).
6. Restart `emma65` (same command as above). Within about a second the
   status should flip back to `connected` in green, with no need to
   restart the peripheral.
7. Close the peripheral window (window-close button) and confirm it exits
   cleanly.
