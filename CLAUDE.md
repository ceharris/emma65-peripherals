# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

External peripherals for [emma65](https://github.com/ceharris/emma65-rust) bus devices (VIA, PTM, ...). Each peripheral is a standalone Python program that connects to an emulator device's transport and speaks its wire protocol; **none of them run inside the emulator process** — they are separate OS processes talking over a socket.

This is a [`uv` workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): each peripheral is its own top-level package with its own `pyproject.toml` and dependencies, since different peripherals use different UI toolkits (`pygame-ce`, Kivy, Textual, curses, ...). The workspace root `pyproject.toml` just declares `members = ["*"]`.

## Commands

```bash
uv sync                                                  # install/sync all workspace packages
uv run --package emma65-buttons emma65-buttons --help    # run a peripheral
uv run --package emma65-buttons emma65-buttons           # run with defaults
uv run pytest                                            # run tests for every package, from the repo root
```

Tests live in a `tests/` directory alongside each package's `src/` (e.g. `via/tests/test_ascii_client.py`) — `pytest` is a workspace-level dev-dependency (root `pyproject.toml`'s `[dependency-groups]`), so `uv run pytest` from the repo root discovers and runs every package's tests in one invocation; don't add a per-package pytest config. GitHub Actions (`.github/workflows/ci.yml`) runs `uv sync && uv run pytest` on push/PR. There is no lint/type-check tooling configured yet — don't assume `ruff`/etc. are set up unless you find config for them.

## Architecture

- **`via/` (`emma65-via`)** — shared client library for the VIA peer protocol's ASCII wire encoding, used by every VIA-based peripheral. `ViaAsciiClient` (`via/src/emma65_via/ascii_client.py`) is a small non-blocking wrapper around a Unix-domain socket: `connect()` (non-blocking, returns `False` if the socket isn't up yet), `set_bits`/`reset_bits` (sends `S`/`R` ASCII messages for a port + bit mask), and `drain()` (discards inbound bytes, raising `ConnectionError` if the peer closed). This client only ever writes; it never parses what it reads back.
- **`buttons/` (`emma65-buttons`)** — first real peripheral, built on `pygame-ce`. `app.py` has three layers worth knowing about:
  - `parse_args` — CLI options (`--socket`, `--via-port`, `--push-bit`, `--toggle-bit`).
  - `ButtonPeripheral` — owns the `ViaAsciiClient` and the two GPIO bits this peripheral drives. Handles reconnection (retries once a second via `connect_if_needed`, driven by `now_ms` from the caller rather than its own clock) and re-asserts current bit state on reconnect so a mid-press/toggle survives a dropped connection.
  - `run` — the pygame event loop: poll for reconnect, pump events, update `ButtonPeripheral` state, redraw, `clock.tick(60)`.
- New peripherals should follow the same shape: a thin UI-toolkit-specific `app.py` on top of a `Peripheral`-style class that owns the `emma65_via` client and only ever touches the specific port bits it's configured for — **peripherals must not touch port bits other than the ones they're explicitly configured to drive**, since a port can be shared with other peripherals driving other bits on the same port.
- Add a new peripheral as a new top-level directory with its own `pyproject.toml` (`[tool.uv.sources] emma65-via = { workspace = true }` to depend on the shared client) and register it in the root `README.md`.

## In-progress work

`gpio-playground/plan/` contains the settled design (`via_gpio_playground_design.md`), UI checkpoint docs recording decisions already made (and alternatives already tried and rejected — read before proposing visual-design changes so you don't re-litigate them), a Pygame mockup (`row_mockup.py`), and a unit-by-unit `via_gpio_playground_implementation_plan.md` for building a more general VIA GPIO panel peripheral (all 8 data pins + CA1/CA2/CB1/CB2 per port, with direction/pin-state indicators), distinct from the simple two-button `buttons` peripheral. `gpio-playground/` itself is excluded from the `uv` workspace (it's plan/mockup content, not a package) — the plan's Unit 2 creates the real package, tentatively named `via-playground/`.
