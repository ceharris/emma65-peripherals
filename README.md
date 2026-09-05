emma65-peripherals
==================

External peripherals for [emma65](https://github.com/ceharris/emma65-rust) bus
devices (VIA, PTM, ...). Each peripheral is a standalone Python program that
connects to an emulator device's transport and speaks its wire protocol;
none of them run inside the emulator process.

This is a [`uv` workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/);
each peripheral is its own top-level package with its own dependencies,
since different peripherals use different UI toolkits (`pygame-ce`, Kivy,
Textual, curses, ...).

## Peripherals

- [`buttons`](buttons) (`emma65-buttons`) — a `pygame-ce` push button and
  toggle button wired to two VIA GPIO pins.

## Running a peripheral

```bash
uv sync
uv run --package emma65-buttons emma65-buttons --help
```
