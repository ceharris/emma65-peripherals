# emma65-buttons

A minimal `pygame-ce` peripheral: a push button and a toggle button, each
wired to one GPIO pin of an emma65 `via/6522` device. It connects as a
client to the VIA's `unix:` transport and speaks the ASCII variant of the
VIA Peer Protocol (see `doc/src/appendix-via-protocol.md` in the emma65
repo).

- **Push button** — asserts its bit while the mouse button is held down over
  it, and releases it on mouse-up.
- **Toggle button** — flips its bit each time it's clicked.

Only the two configured bits are ever touched, so the port can be shared
with other peripherals driving other bits.

## Running

Start (or already have running) an emma65 instance with a `via/6522` device
on a Unix-domain socket, e.g.:

```toml
[[devices]]
type = "via/6522"
address = 0x9000
transport = "unix:~/.emma/sock/via6522"
```

Then, from the workspace root:

```bash
uv run --package emma65-buttons emma65-buttons
```

The peripheral retries the connection once a second until the socket is
available, and reconnects automatically if the emulator restarts.

## Options

```
--socket SOCKET     Unix-domain socket path for the VIA transport
                     (default: ~/.emma/sock/via6522)
--via-port {A,B}    VIA port the buttons are wired to (default: A)
--push-bit 0-7      Port bit driven by the push button (default: 0)
--toggle-bit 0-7    Port bit driven by the toggle button (default: 1)
```
