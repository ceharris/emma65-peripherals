"""Minimal client for the VIA peer protocol's ASCII encoding, over a Unix-domain socket.

See the emma65 project's VIA Peer Protocol appendix for the full wire format.
This client only ever sends Set Port / Reset Port messages for the bits it
owns, and otherwise discards everything it reads.
"""

from __future__ import annotations

import os
import socket


class ViaAsciiClient:
    """A non-blocking client for the VIA peer protocol (ASCII encoding, `unix:` transport)."""

    def __init__(self, path: str):
        self._path = os.path.expanduser(path)
        self._sock: socket.socket | None = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> bool:
        """Attempts to connect. Returns True on success, False if the socket isn't available yet."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._path)
        except OSError:
            sock.close()
            return False
        sock.setblocking(False)
        self._sock = sock
        return True

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def set_bits(self, port: str, mask: int) -> None:
        self._send(f"S{port}{mask:02X}")

    def reset_bits(self, port: str, mask: int) -> None:
        self._send(f"R{port}{mask:02X}")

    def drain(self) -> None:
        """Discards inbound bytes. Raises ConnectionError if the peer closed the connection."""
        assert self._sock is not None
        try:
            while True:
                data = self._sock.recv(4096)
                if not data:
                    self.close()
                    raise ConnectionError("VIA connection closed")
        except BlockingIOError:
            pass

    def _send(self, message: str) -> None:
        assert self._sock is not None
        try:
            self._sock.sendall(message.encode("ascii"))
        except OSError as e:
            self.close()
            raise ConnectionError(str(e)) from e
