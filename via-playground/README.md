# emma65-via-playground

A `pygame-ce` panel for observing and driving every pin of an emma65 `via/6522`
device (all 8 data pins plus CA1/CA2/CB1/CB2 on both ports). It connects as a
client to the VIA's `unix:` transport and speaks the ASCII variant of the VIA
Peer Protocol (see `doc/src/appendix-via-protocol.md` in the emma65 repo), via
the shared `emma65-via` client library.

This is Unit 3 of the [GPIO playground implementation
plan](../gpio-playground/plan/via_gpio_playground_implementation_plan.md).
The window renders a static Port A row (PA0-PA7, CA1, CA2) built on a
reusable `Cell`/`DataCell`/`ControlCell` widget hierarchy (see
`src/emma65_via_playground/cells.py`), plus connection status -- pin state is
still placeholder data, and interactivity lands in later units.

## Running

Start (or already have running) an emma65 instance with a `via/6522` device
on a Unix-domain socket, e.g.:

```toml
[[devices]]
type = "via/6522"
address = 0x9000
transport = "unix:~/.emma/sock/via6522"
protocol = "ascii"
```

Then, from the workspace root:

```bash
uv run --package emma65-via-playground emma65-via-playground
```

The peripheral retries the connection once a second until the socket is
available, and reconnects automatically if the emulator restarts.

## Options

```
--socket SOCKET     Unix-domain socket path for the VIA transport
                     (default: ~/.emma/sock/via6522)
```
