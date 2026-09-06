# emma65-via-playground

A `pygame-ce` panel for observing and driving every pin of an emma65 `via/6522`
device (all 8 data pins plus CA1/CA2/CB1/CB2 on both ports). It connects as a
client to the VIA's `unix:` transport and speaks the ASCII variant of the VIA
Peer Protocol (see `doc/src/appendix-via-protocol.md` in the emma65 repo), via
the shared `emma65-via` client library.

This is Unit 4 of the [GPIO playground implementation
plan](../gpio-playground/plan/via_gpio_playground_implementation_plan.md).
The window renders a Port A row (PA0-PA7, CA1, CA2) built on a reusable
`Cell`/`DataCell`/`ControlCell` widget hierarchy (see
`src/emma65_via_playground/cells.py`), plus connection status. The PA0-PA7
chevron now tracks live pin level from the VIA; direction and local
(toggle/momentary) state are still placeholders -- interactivity lands in
Unit 5.

**Direction is declared, not read.** The VIA peer protocol never conveys DDR
(or ACR/PCR) contents -- it only ever reports pin *levels* -- so this
peripheral can't know which way a pin is actually configured, the same way
an external device wired to a real 6522's GPIO pins can't query its DDR
register. `--pa-direction` lets you tell the panel what you expect PA0-PA7's
direction to be, to match your ROM's actual configuration; if it's wrong,
you'll see it as chevron/LED divergence (and, from Unit 10 on, the Overload
indicator) rather than an error -- the panel doesn't prevent
misconfiguration, mirroring real hardware.

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
--socket SOCKET       Unix-domain socket path for the VIA transport
                       (default: ~/.emma/sock/via6522)
--pa-direction HEX    Declared DDRA value for Port A data pins, as a hex
                       byte -- bit n set means PAn is an output
                       (default: F0, i.e. PA7-PA4 out, PA3-PA0 in)
```
