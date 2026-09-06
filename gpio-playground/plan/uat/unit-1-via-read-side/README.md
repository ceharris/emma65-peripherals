# UAT: Unit 1 -- VIA protocol read-side support

Throwaway verification material for Unit 1 (`emma65_via.protocol.AsciiEventDecoder`
and `ViaAsciiClient.poll()`). Not part of any package -- exercises the new
read side against a live VIA socket, driven by a small 6502 program that
toggles Port A's data pins and CA2.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-1-via-read-side
ca65 -g --cpu w65c02 via_read_uat.s -o via_read_uat.o
ld65 --config via_read_uat.cfg via_read_uat.o -o via_read_uat.bin
```

## Run the emulator

There is no `emma65` on `$PATH` by default -- build one from current
`emma65-rust` source:

```bash
cd path/to/emma65-rust   # the emma65 (Rust) checkout, not this repo
cargo build
target/debug/emma65 --config path/to/emulator.toml
```

**Note:** as of 2026-09-06, a stale prebuilt `emma65` (previously at
`~/bin/emma65`, dated 2026-06-22) was found to predate the VIA peer
protocol's connect-time state dump -- against that build, a peer socket
connects fine but never receives any bytes, even the documented initial
`PortState`/`CtrlState` dump. It's since been removed, but if `emma65`
ever reappears on `$PATH` and this UAT seems to hang with no traffic,
suspect a stale build before suspecting the Python code.

## Watch decoded events

In another terminal, from the `emma65-peripherals` repo root:

```bash
uv run --package emma65-via python gpio-playground/plan/uat/unit-1-via-read-side/watch_events.py
```

Expect, in order:
1. On connect: a full state dump -- `PortState`/`CtrlState` for both ports
   (reflecting whatever the program has already set by the time you connect).
2. Then, roughly once a second: `PortState(port='A', level=...)` alternating
   between `0x55` and `0xAA` as the program flips Port A's data pins, paired
   with `CtrlPinSet(port='A', pin=2)` / `CtrlPinReset(port='A', pin=2)` as it
   drives CA2 (manual output mode) high and low.

Ctrl-C the watcher when satisfied; kill the `emma65` process separately.
