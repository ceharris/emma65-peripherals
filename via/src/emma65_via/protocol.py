"""Event types and decoder for the read side of the VIA peer protocol's ASCII encoding.

See the emma65 project's VIA Peer Protocol appendix for the full wire format.
On connect, the VIA sends a full state dump (`PortState`/`CtrlState` for both
ports); after that, it sends incremental `Set`/`Reset` messages as pins
change. `AsciiEventDecoder` mirrors the decoder state machine in emma65-rust's
`emulator::device::protocol::via` module byte-for-byte, including its
silently-discard-invalid-input behavior.

DDR/ACR/PCR register contents are not part of this protocol, so direction and
timer/pulse-mode state can't be derived from anything here -- a peripheral
that needs those has to track them some other way. See Unit 1 of the VIA GPIO
playground implementation plan for the gap this leaves for later units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class PortState:
    """Full 8-bit state of a port (`pxx`), sent when a peripheral connects."""

    port: str
    level: int


@dataclass(frozen=True)
class CtrlState:
    """Full state of a port's control pins (`Cpuv`), sent when a peripheral connects."""

    port: str
    c1: bool
    c2: bool


@dataclass(frozen=True)
class PortBitsSet:
    """Bits of a port's data pins that have gone high (`Spxx`)."""

    port: str
    mask: int


@dataclass(frozen=True)
class PortBitsReset:
    """Bits of a port's data pins that have gone low (`Rpxx`)."""

    port: str
    mask: int


@dataclass(frozen=True)
class CtrlPinSet:
    """A control pin (`1` or `2`) that has gone high (`SCpu`)."""

    port: str
    pin: int


@dataclass(frozen=True)
class CtrlPinReset:
    """A control pin (`1` or `2`) that has gone low (`RCpu`)."""

    port: str
    pin: int


ViaEvent = Union[PortState, CtrlState, PortBitsSet, PortBitsReset, CtrlPinSet, CtrlPinReset]


def _hex_nibble(ch: str) -> int | None:
    if "0" <= ch <= "9":
        return ord(ch) - ord("0")
    if "A" <= ch <= "F":
        return ord(ch) - ord("A") + 10
    if "a" <= ch <= "f":
        return ord(ch) - ord("a") + 10
    return None


class AsciiEventDecoder:
    """Feeds inbound bytes one at a time, decoding recognized VIA protocol messages.

    Invalid or unrecognized input is silently discarded, per the protocol
    spec, and simply aborts whatever message was in progress.
    """

    def __init__(self) -> None:
        self._state: tuple = ("idle",)

    def feed(self, byte: int) -> ViaEvent | None:
        """Feeds one inbound byte. Returns a decoded event once a message completes."""
        ch = chr(byte)
        upper = ch.upper()
        state = self._state
        name = state[0]

        if name == "idle":
            if upper in ("A", "B"):
                self._state = ("port_state", upper)
            elif upper == "C":
                self._state = ("ctrl_state",)
            elif upper == "R":
                self._state = ("reset",)
            elif upper == "S":
                self._state = ("set",)
            return None

        if name == "port_state":
            port = state[1]
            nibble = _hex_nibble(ch)
            self._state = ("port_state_high", port, nibble) if nibble is not None else ("idle",)
            return None

        if name == "port_state_high":
            port, high = state[1], state[2]
            self._state = ("idle",)
            low = _hex_nibble(ch)
            return None if low is None else PortState(port=port, level=(high << 4) | low)

        if name == "ctrl_state":
            if upper in ("A", "B"):
                self._state = ("ctrl_state_port", upper)
            else:
                self._state = ("idle",)
            return None

        if name == "ctrl_state_port":
            port = state[1]
            if ch in ("0", "1"):
                self._state = ("ctrl_state_pin1", port, ch == "1")
            else:
                self._state = ("idle",)
            return None

        if name == "ctrl_state_pin1":
            port, c1 = state[1], state[2]
            self._state = ("idle",)
            if ch in ("0", "1"):
                return CtrlState(port=port, c1=c1, c2=(ch == "1"))
            return None

        if name == "reset":
            if upper in ("A", "B"):
                self._state = ("reset_port", upper)
            elif upper == "C":
                self._state = ("reset_ctrl",)
            else:
                self._state = ("idle",)
            return None

        if name == "reset_port":
            port = state[1]
            nibble = _hex_nibble(ch)
            self._state = ("reset_port_high", port, nibble) if nibble is not None else ("idle",)
            return None

        if name == "reset_port_high":
            port, high = state[1], state[2]
            self._state = ("idle",)
            low = _hex_nibble(ch)
            return None if low is None else PortBitsReset(port=port, mask=(high << 4) | low)

        if name == "set":
            if upper in ("A", "B"):
                self._state = ("set_port", upper)
            elif upper == "C":
                self._state = ("set_ctrl",)
            else:
                self._state = ("idle",)
            return None

        if name == "set_port":
            port = state[1]
            nibble = _hex_nibble(ch)
            self._state = ("set_port_high", port, nibble) if nibble is not None else ("idle",)
            return None

        if name == "set_port_high":
            port, high = state[1], state[2]
            self._state = ("idle",)
            low = _hex_nibble(ch)
            return None if low is None else PortBitsSet(port=port, mask=(high << 4) | low)

        if name == "reset_ctrl":
            if upper in ("A", "B"):
                self._state = ("reset_ctrl_port", upper)
            else:
                self._state = ("idle",)
            return None

        if name == "reset_ctrl_port":
            port = state[1]
            self._state = ("idle",)
            return CtrlPinReset(port=port, pin=int(ch)) if ch in ("1", "2") else None

        if name == "set_ctrl":
            if upper in ("A", "B"):
                self._state = ("set_ctrl_port", upper)
            else:
                self._state = ("idle",)
            return None

        if name == "set_ctrl_port":
            port = state[1]
            self._state = ("idle",)
            return CtrlPinSet(port=port, pin=int(ch)) if ch in ("1", "2") else None

        self._state = ("idle",)  # pragma: no cover - unreachable
        return None
