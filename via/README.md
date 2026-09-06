# emma65-via

Shared client for the [emma65](https://github.com/ceharris/emma65-rust) VIA
peer protocol's ASCII encoding, used by every VIA-based peripheral in this
workspace. See the emma65 project's VIA Peer Protocol appendix for the full
wire format.

```python
from emma65_via import ViaAsciiClient

client = ViaAsciiClient("~/.emma/sock/via6522")
client.connect()  # non-blocking; returns False if the socket isn't up yet
```

## Write side

`set_bits(port, mask)` / `reset_bits(port, mask)` send `S`/`R` messages for
the given port (`"A"` or `"B"`) and bit mask. `set_ctrl_pin(port, pin)` /
`reset_ctrl_pin(port, pin)` send the equivalent `SC`/`RC` messages for a
single control pin (`1` or `2`) instead of a data-bit mask. A peripheral
should only ever set/reset the bits or control pins it's configured to
drive — a port can be shared with other peripherals driving other bits.

## Read side

`poll() -> list[ViaEvent]` reads whatever the VIA has sent since the last
call and decodes it into a list of typed events, in wire order:

| Event           | Fields             | Wire message | Meaning                                   |
|-----------------|--------------------|--------------|--------------------------------------------|
| `PortState`     | `port`, `level`    | `pxx`        | Full 8-bit port state, sent on connect     |
| `CtrlState`     | `port`, `c1`, `c2` | `Cpuv`       | Full control-pin state, sent on connect    |
| `PortBitsSet`   | `port`, `mask`     | `Spxx`       | Data bits that went high                   |
| `PortBitsReset` | `port`, `mask`     | `Rpxx`       | Data bits that went low                    |
| `CtrlPinSet`    | `port`, `pin`      | `SCpu`       | Control pin (`1`/`2`) went high            |
| `CtrlPinReset`  | `port`, `pin`      | `RCpu`       | Control pin (`1`/`2`) went low             |

On connect, the VIA immediately sends a full state dump (`PortState` and
`CtrlState` for both ports) so a peripheral starts with an accurate picture
without waiting for the next change. After that, ongoing changes arrive as
some mix of full `PortState`/`CtrlState` re-dumps and incremental
`PortBitsSet`/`PortBitsReset`/`CtrlPinSet`/`CtrlPinReset` messages -- observed
live traffic shows data-port changes tend to resend the full `PortState`
while control-pin changes come as individual `CtrlPinSet`/`CtrlPinReset`
events, but nothing in the protocol guarantees that split. A peripheral that
wants to track live port/control state should handle every event type and
just apply each one to a local copy in order.

`poll()` is non-blocking and raises `ConnectionError` if the peer has closed
the connection (same as `set_bits`/`reset_bits`). `drain()` remains available
as a thin wrapper that calls `poll()` and discards the result, for callers
that don't care about inbound state.

**Gap:** this protocol only reports data-pin and control-pin *levels* — it
has no message for DDR, ACR, or PCR register contents. A peripheral that
needs to know a pin's *direction*, or whether a timer/pulse mode is active,
can't derive it from anything `emma65_via` exposes today; see the VIA GPIO
playground implementation plan for how later units work around or close this
gap.

## Decoding directly

`AsciiEventDecoder` (in `emma65_via.protocol`) is the standalone byte-at-a-time
decoder `ViaAsciiClient.poll()` uses internally. It's exposed separately
because it's pure decode logic with no socket dependency — useful for tests,
or for a peripheral that manages its own I/O:

```python
from emma65_via import AsciiEventDecoder

decoder = AsciiEventDecoder()
for byte in inbound_bytes:
    event = decoder.feed(byte)
    if event is not None:
        handle(event)
```
