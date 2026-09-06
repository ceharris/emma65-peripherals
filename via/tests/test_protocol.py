"""Tests for the VIA ASCII protocol's read-side event decoder."""

from __future__ import annotations

from emma65_via.protocol import (
    AsciiEventDecoder,
    CtrlPinReset,
    CtrlPinSet,
    CtrlState,
    PortBitsReset,
    PortBitsSet,
    PortState,
)


def feed_str(decoder: AsciiEventDecoder, message: str) -> list:
    events = []
    for byte in message.encode("ascii"):
        event = decoder.feed(byte)
        if event is not None:
            events.append(event)
    return events


def test_decodes_port_a_state():
    events = feed_str(AsciiEventDecoder(), "A55")
    assert events == [PortState(port="A", level=0x55)]


def test_decodes_port_b_state():
    events = feed_str(AsciiEventDecoder(), "BAA")
    assert events == [PortState(port="B", level=0xAA)]


def test_decodes_port_state_is_case_insensitive_and_accepts_lowercase_hex():
    events = feed_str(AsciiEventDecoder(), "a5a")
    assert events == [PortState(port="A", level=0x5A)]


def test_decodes_ctrl_state():
    events = feed_str(AsciiEventDecoder(), "CA10")
    assert events == [CtrlState(port="A", c1=True, c2=False)]
    events = feed_str(AsciiEventDecoder(), "CB01")
    assert events == [CtrlState(port="B", c1=False, c2=True)]


def test_decodes_reset_port():
    events = feed_str(AsciiEventDecoder(), "RBF0")
    assert events == [PortBitsReset(port="B", mask=0xF0)]


def test_decodes_set_port():
    events = feed_str(AsciiEventDecoder(), "SA03")
    assert events == [PortBitsSet(port="A", mask=0x03)]


def test_decodes_reset_ctrl():
    events = feed_str(AsciiEventDecoder(), "RCA2")
    assert events == [CtrlPinReset(port="A", pin=2)]


def test_decodes_set_ctrl():
    events = feed_str(AsciiEventDecoder(), "SCB1")
    assert events == [CtrlPinSet(port="B", pin=1)]


def test_ignores_separator_spaces_between_messages():
    events = feed_str(AsciiEventDecoder(), "A55 SA03 RCA2 ")
    assert events == [
        PortState(port="A", level=0x55),
        PortBitsSet(port="A", mask=0x03),
        CtrlPinReset(port="A", pin=2),
    ]


def test_ignores_canonical_newline_between_messages():
    events = feed_str(AsciiEventDecoder(), "A55 \r\nSA03 ")
    assert events == [
        PortState(port="A", level=0x55),
        PortBitsSet(port="A", mask=0x03),
    ]


def test_discards_invalid_port_letter():
    events = feed_str(AsciiEventDecoder(), "Z55A55")
    assert events == [PortState(port="A", level=0x55)]


def test_discards_incomplete_message_and_resumes_at_next_valid_prefix():
    decoder = AsciiEventDecoder()
    assert decoder.feed(ord("A")) is None
    assert decoder.feed(ord("5")) is None
    # A non-hex byte here aborts the in-progress PortState message.
    assert decoder.feed(ord("!")) is None
    events = feed_str(decoder, "B0F")
    assert events == [PortState(port="B", level=0x0F)]


def test_discards_invalid_ctrl_pin_digit():
    events = feed_str(AsciiEventDecoder(), "SCA9SCA1")
    assert events == [CtrlPinSet(port="A", pin=1)]


def test_feed_returns_none_while_message_is_incomplete():
    decoder = AsciiEventDecoder()
    assert decoder.feed(ord("A")) is None
    assert decoder.feed(ord("5")) is None
