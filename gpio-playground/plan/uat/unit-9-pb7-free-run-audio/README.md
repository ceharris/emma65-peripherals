# UAT: Unit 9 -- PB7 free-run indicator and audio output

Throwaway verification material for Unit 9
(`via-playground/src/emma65_via_playground/cells.py`'s `PB7Cell`,
`app.py`'s `PB7State`/`Pb7Audio`/`toggle_pb7_speaker`).

This unit adds PB7's T1-free-run informational badge and a speaker icon that
routes a naive square-wave audio reconstruction of PB7's live wire level.

## Run the peripheral

This ROM declares **DDRA=$00 and DDRB=$00 -- every PAx/PBx bit, including
PB7, is a VIA input** -- deliberately, to demonstrate that Timer 1's PB7
square-wave output overrides DDRB7 entirely (confirmed against
`emma65-rust`'s own `via6522.rs`: "square wave output mode takes priority
over ... DDRB bit 7"). This ROM doesn't configure T2 pulse-counting mode
either, so disable PB6's declared pulse-counting to avoid an unrelated
declared/real mismatch distracting from what this unit is testing:

```bash
uv run --package emma65-via-playground emma65-via-playground \
    --pb-direction 38 --no-pb6-pulse-counting --pb7-free-run
```

`--pb-direction 38` declares PB7 as an **input** on the panel side even
though it's genuinely being driven -- the point of this specific mask,
not an oversight. `--pb7-free-run` lights the informational "T1" badge;
it's a declared, CLI-level setting (same reasoning as
`--pb6-pulse-counting`), not something read live from the VIA, since the
wire protocol never reports ACR.

## What the ROM does

Configures ACR bits 7 and 6 (`%11000000`) -- Timer 1's free-run mode with
PB7 square-wave output enabled -- then loads T1 with a reload value of 2095
cycles and idles forever. At this UAT's `clock-speed-hz` (1843200), that
produces a square wave at `1843200 / (2 * 2095) ~= 439.9 Hz`, close to
musical A4. T1's free-run mode needs no further CPU involvement once
started; the tone runs entirely in VIA hardware. The ROM prints one
confirmation line (`T1 free-run: ACR=C0 T1=082F`) to the emulator's
`console` device on boot.

**Self-check already done by the agent, headlessly, before this handoff:**
connected directly to the running emulator's socket and measured PB7's
actual toggle rate over a 1-second window: 879 toggles observed, mean
half-period 1.137ms, implied frequency 439.8 Hz -- matches the computed
439.9 Hz almost exactly. Also ran `via-playground`'s own `Peripheral.poll()`
against the live socket and confirmed `ports["B"].level` bit 7 genuinely
toggles through the full event-decode path, and that `Pb7Audio` degrades
cleanly (`_stream is None`) in this sandbox's no-PortAudio environment
without raising. What's left for human verification below is the part the
agent cannot do itself: whether the reconstructed square wave is actually
audible and sounds right, and the visual widgets render/click correctly.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-9-pb7-free-run-audio
ca65 -g --cpu w65c02 unit9_uat.s -o unit9_uat.o
ld65 --config unit9_uat.cfg unit9_uat.o -o unit9_uat.bin
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
terminal into raw mode; you won't see the boot banner otherwise.

## Check the window, console, and speakers

Launch the peripheral as shown above.

### Visual: PB7's anatomy

1. **PB7 keeps its LED, chevron, toggle, and momentary button** in the same
   positions as any other data cell. Its chevron shows a live "in" arrow
   (apex up, per the declared `--pb-direction 38`) whose fill tracks the
   actual toggling pin level -- it should visibly flicker (too fast to
   follow individual transitions at ~440Hz, but should look "busy"/blurred
   rather than static).
2. **A small amber "T1" badge** appears where PB6's PLS/LVL display would
   be (one gap above the speaker icon) -- bright since `--pb7-free-run` was
   passed. Unlike PB6's mode display, clicking it does nothing (it's
   read-only).
3. **A violet speaker icon** appears below the T1 badge, in the same slot
   CA1/CA2/CB1/CB2 use for their polarity icon -- lit (box+cone+wave arcs)
   by default since audio routing starts on.

### Audio: tone on, tone off

4. **You should hear a continuous, roughly-440Hz tone** as soon as the
   peripheral connects (assuming your machine has a working audio output
   device -- the agent's own sandbox does not, so this step is entirely on
   you).
5. **Click the speaker icon.** It should switch to its muted rendering (dim
   fill, single bright diagonal stroke through it, per checkpoint 2) and
   the tone should stop immediately. Click it again: the icon relights and
   the tone resumes.

### Declared-off comparison (informational badge only)

6. **Stop the peripheral and relaunch without `--pb7-free-run`** (leave the
   emulator/ROM running -- it doesn't know or care what the panel
   declares). The "T1" badge should now render dim instead of bright. The
   tone should still play exactly as before (the badge is purely
   informational and never gates the audio reconstruction, which only
   depends on the actual wire level and the speaker icon's own on/off
   state) -- a declared/real mismatch here shows up only in the badge's
   brightness, matching the panel's whole misconfiguration philosophy.

### Reconnect

7. With the peripheral connected and playing tone, kill and restart
   `emma65` mid-session. Connection status should flip to `connecting...`
   and back. Once reconnected and the ROM has re-run its setup, the tone
   should resume (there is nothing PB7-specific to reassert on reconnect --
   `Pb7Audio` just keeps reading `ports["B"].level` live, and the VIA's own
   post-connect `PortState` dump will reflect T1's current PB7 state).
