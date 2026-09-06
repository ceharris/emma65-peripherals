# UAT: Unit 8 -- PB6 pulse-counting layered behavior

Throwaway verification material for Unit 8
(`via-playground/src/emma65_via_playground/cells.py`'s `PB6Cell`,
`app.py`'s `PB6State`/`press_pb6`/`release_pb6`/`toggle_pb6_mode`).

This unit layers T2 pulse-counting behavior onto PB6: forced pulled up,
and its toggle repurposed into a PLS/LVL mode-select for the momentary
(same widget CB1/CB2 use).

## Run the peripheral

This ROM declares **DDRA=$00 and DDRB=$00 -- every PAx/PBx bit, including
PB6, is a VIA input** (real hardware wires PB6 as an input driven by
whatever's doing the counting). Match the peripheral's declared direction:

```bash
uv run --package emma65-via-playground emma65-via-playground --pb-direction 00
```

`--pb6-pulse-counting` defaults to **on**, matching this ROM's ACR
configuration, so no extra flag is needed for the main walkthrough below.
A second walkthrough (step 7) asks you to relaunch with
`--no-pb6-pulse-counting` to check the declared-off behavior.

## What the ROM does

Configures ACR bit 5 (`%00100000`) -- Timer 2's pulse-counting mode, which
makes T2 count every high-to-low transition on PB6, exactly the real 6522
behavior this panel is demonstrating. T2 is loaded with a small count (5)
so a handful of clicks is enough to walk it down to a wrap, and the ROM
automatically reloads it to 5 every time it wraps. It prints to the
emulator's `console` device whenever:

- `Txx` -- T2's low counter byte changed to `xx` (one decrement per PB6
  high-to-low edge -- i.e. per momentary press's *leading* edge, in both
  level and pulse mode; releases don't count, since they're low-to-high)
- `Wxx` -- T2 just wrapped (its own IFR flag fired), printed once with
  `xx` = `FF` (the underflowed value), always immediately followed by a
  `Txx` line showing the reload back to 5
- `Pxx` -- PB6 alone (`ORB & $40`) changed to `xx` (`40` = idle/pulled-up,
  `00` = active/low)

Reading T2's low counter byte clears T2's own IFR flag as a side effect on
real 6522 hardware (same as ORA/ORB clearing CA1/CA2/CB1/CB2, the ordering
lesson from Unit 7's UAT) -- the ROM reads IFR before T2C-L each iteration
so a wrap landing between iterations is never silently missed.

## Build the 6502 test program

Requires `ca65`/`ld65` (the `cc65` toolchain):

```bash
cd gpio-playground/plan/uat/unit-8-pb6-pulse-counting
ca65 -g --cpu w65c02 unit8_uat.s -o unit8_uat.o
ld65 --config unit8_uat.cfg unit8_uat.o -o unit8_uat.bin
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

## Check the window and console

Launch the peripheral as shown above (`--pb-direction 00`).

### Visual: PB6's layered anatomy

1. **PB6 keeps its LED, chevron, and momentary button** in the same
   positions as any other data cell. Its chevron shows a live "in" arrow
   (apex up) tracking `ORB` bit 6, same as PB0-PB5.
2. **PB6's toggle is replaced by a toggle + PLS/LVL segment display**,
   positioned exactly like CB1/CB2's mode selector -- starts in `LVL`.

### Interactive: level mode, walking the counter to a wrap

3. With PB6 still in `LVL` mode, **click-and-release PB6's momentary once**.
   Console should print `P00` (pin went low) then `T04` (T2 decremented
   from its initial 5). LED should dim/light appropriately as the pin
   goes low then `P40` should print on release (T2 does not decrement
   again on release -- rising edges aren't counted).
4. **Repeat four more times** (five presses total). After the fifth press
   you should see `T00`. After a **sixth** press, you should see `Wff`
   immediately followed by `T05` -- the wrap event, then the automatic
   reload back to 5.
5. **Press-and-hold** PB6's momentary for a couple of seconds, then
   release. Console should show exactly one `T` decrement for the press
   (the falling edge) and none for the release or for the duration held --
   holding does not cause repeated counting.

### Interactive: pulse mode

6. **Click PB6's mode toggle** to switch to `PLS`. A single quick click
   (or a click-and-hold, doesn't matter -- pulse mode ignores hold time)
   of the momentary should produce exactly one `T` decrement, followed
   ~100ms later by the automatic revert back to pulled-up (`P40`), with no
   second decrement from the revert.

### Declared-off comparison

7. **Stop the peripheral and relaunch with `--no-pb6-pulse-counting`**
   (leave the emulator/ROM running -- it doesn't know or care what the
   panel declares, which is the point). PB6 should now render and behave
   like an **ordinary data cell**: a plain local-pull toggle (no PLS/LVL
   display), and clicking its toggle flips `local` directly instead of a
   mode. Despite the panel no longer declaring pulse-counting, **clicking
   PB6's toggle or momentary still produces real `T`/`W` console lines** --
   the real (simulated) VIA doesn't care what the panel thinks PB6 is for,
   only what's actually wired to it; a declared/real mismatch shows up as
   behavior, not an error, matching the panel's whole misconfiguration
   philosophy.

### Reconnect

8. With PB6 pulled up as usual (declared on), kill and restart `emma65`
   mid-session. Connection status should flip to `connecting...` and back;
   PB6 should reassert forced-pulled-up (`P40` shortly after reconnect, if
   it wasn't already at that level) and the mode selector's state
   (PLS/LVL) should be unchanged on screen.
