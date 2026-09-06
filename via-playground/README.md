# emma65-via-playground

A `pygame-ce` panel for observing and driving every pin of an emma65 `via/6522`
device (all 8 data pins plus CA1/CA2/CB1/CB2 on both ports). It connects as a
client to the VIA's `unix:` transport and speaks the ASCII variant of the VIA
Peer Protocol (see `doc/src/appendix-via-protocol.md` in the emma65 repo), via
the shared `emma65-via` client library.

This is Unit 2 of the [GPIO playground implementation
plan](../gpio-playground/plan/via_gpio_playground_implementation_plan.md): it
proves the connection plumbing end-to-end. The window shows connection status
and draws nothing else yet -- pin cells and interactivity land in later units.

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
