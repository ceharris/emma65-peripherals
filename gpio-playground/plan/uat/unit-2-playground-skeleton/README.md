# UAT: Unit 2 -- new peripheral skeleton (emma65-via-playground)

Throwaway verification material for Unit 2. This unit only proves the
peripheral's connection plumbing end-to-end -- there's no pin traffic to
observe yet, so the 6502 program here does nothing but keep the CPU running
while a `via/6522` device's socket stays up.

The connect/reconnect logic itself (`Peripheral.connect_if_needed`/`poll`)
is unit-tested (`via-playground/tests/test_via_playground_app.py`) and was
also self-verified headlessly against a live socket. What's left to check by
hand is the pygame window: does it actually open, and does the on-screen
status text track the socket going up and down.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-2-playground-skeleton
ca65 -g --cpu w65c02 unit2_uat.s -o unit2_uat.o
ld65 --config unit2_uat.cfg unit2_uat.o -o unit2_uat.bin
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

Check:
1. A window titled "emma65 VIA GPIO playground" opens, showing centered
   status text reading `connected  (~/.emma/sock/via6522)` in green.
2. Kill the `emma65` process (Ctrl-C in its terminal). Within about a
   second the status text should flip to `connecting...` in red.
3. Restart `emma65` (same command as above). Within about a second the
   status should flip back to `connected` in green, with no need to
   restart the peripheral.
4. Close the peripheral window (window-close button) and confirm it exits
   cleanly.
