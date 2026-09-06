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

**Self-check done by the agent before this handoff.** Getting a genuinely
correct tone took three iterations, each one caught only by actually
measuring the live signal or the actual rendered audio -- not by reasoning
about the code -- and the last one needed a second opinion from a research
pass, since the symptom (a Python thread's writes barely visible to an
audio callback) pointed at several plausible but wrong culprits:

1. **First bug:** `Pb7Audio` originally sampled `port_b.level`, which the
   main render loop only updates once per ~16.7ms frame (`clock.tick(60)`)
   -- roughly 15 real PB7 transitions land in a single `poll()` call and
   all but the last are discarded. Fixed by giving `Pb7Audio` its own
   independent, read-only connection to the VIA (multi-peer is supported
   -- confirmed against emma65-rust's `ProtocolManager::send_to_all`),
   read from a dedicated background thread.
2. **Second bug, surfaced by re-measuring after (1):** the human reported
   the result was audible but still didn't resemble a square wave. Traced
   (with help from a research pass into `sounddevice`/PortAudio's actual
   implementation) to PortAudio's buffer processor: when the requested
   `blocksize` is smaller than the host's own negotiated period, it slices
   one host-period callback into several Python invocations fired back to
   back in a sub-millisecond burst, then goes quiet until the next host
   period (documented PortAudio behavior, not a bug in this code) --
   confirmed directly by timestamping a bare `sd.OutputStream` callback
   (~13 calls within ~150us, then a ~10.6ms gap, repeating). A separate,
   more fundamental problem sat underneath that: sampling "the current
   level" once per callback and holding it flat across the whole block is
   wrong regardless of how small the block is or how fresh the input is
   -- it always aliases an ~880 transitions/sec signal down to whatever
   the effective callback rate is.
3. **The actual fix:** `Pb7Audio` now renders each transition into a ring
   buffer the instant its dedicated reader thread decodes it (timestamped
   with `time.perf_counter()`), and the audio callback is a dumb reader
   that copies sequential samples out from a position held a fixed
   `PB7_AUDIO_JITTER_MS` (15ms) behind the write position -- the two
   threads never hand off a single "current value" at all, so there's
   nothing for a callback-timing quirk to alias. `blocksize` is left at
   PortAudio's own default per its documented recommendation ("the most
   robust behavior can be achieved by using blocksize=0"); precision now
   lives entirely in the recorded edge timestamps, not callback frequency.

Verified after the fix, fully isolated from any live emulator (a synthetic
producer thread emitting real ~880 transitions/sec with realistic
scheduling jitter, feeding `Pb7Audio` exactly as the real reader thread
would): captured the actual samples written to a real audio device over
1 second and confirmed 879 zero-crossings, a 440.05Hz frequency estimate
-- matching the driven frequency almost exactly, with a real
`sd.OutputStream` and no artificial shortcuts.

4. **Known, accepted residual limitation, confirmed and not further
   fixable in this peripheral:** against the *real* emulator, the human
   still heard a recognizable but somewhat rough/flat tone (measured:
   ~431Hz instead of ~440Hz, with real half-period jitter). Traced to the
   wall-clock arrival timing of the VIA's own broadcast messages, not to
   anything downstream: a bare blocking `recv()` loop with nothing else
   running already shows ~0.65ms stdev on PB7's ~1.14ms half-period,
   essentially matching the full running app (~0.77ms) -- zero underruns
   or resyncs either way, so it isn't `Pb7Audio`'s reader thread or the
   render loop falling behind. `emma65` maintains cycle-accurate emulation
   internally, but as an ordinary (non-realtime-scheduled) OS process its
   wall-clock message timing still inherits whatever the OS scheduler does
   to it -- exactly the design doc's own named risk ("jitter/coalescing
   from socket delivery timing, GC pauses, OS scheduling, etc."). Its
   proposed remedy is a dedicated transport carrying the emulator's
   *cycle count* per edge instead of a wall-clock timestamp -- a
   `emma65-rust` wire-protocol change, out of scope for this peripheral.
   Accepted as Unit 9's scoped deliverable rather than chased further.

What's left for human verification below is the part the agent genuinely
cannot do itself: confirming the tone is now recognizable (not the
unrecognizable noise from earlier iterations) and that the visual widgets
render/click correctly. Don't expect audiophile-grade purity -- see (4).

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

4. **You should hear a continuous, recognizable square-wave-ish tone in
   the neighborhood of 440Hz** as soon as the peripheral connects
   (assuming your machine has a working audio output device and
   `libportaudio2` installed -- on Linux, `sudo apt install
   libportaudio2` if the peripheral's own terminal prints a "PB7 audio
   disabled" line). It won't be a pure, perfectly steady tone -- some
   roughness and mild pitch drift are expected and accepted; see the
   "Known, accepted residual limitation" note above. What you're checking
   here is that it's clearly a recognizable tone, not unintelligible
   noise/static.
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
