"""Tests for ButtonPeripheral's push/toggle bit-mask logic and reconnect behavior."""

from __future__ import annotations

import socket

import pytest

from emma65_buttons.app import ButtonPeripheral, parse_args


@pytest.fixture
def via_server(tmp_path):
    """A listening Unix-domain socket standing in for the VIA transport."""
    sock_path = str(tmp_path / "via.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)
    yield sock_path, server
    server.close()


def _make_peripheral(sock_path, server, **kwargs):
    argv = ["--socket", sock_path]
    for flag, value in kwargs.items():
        argv += [f"--{flag.replace('_', '-')}", str(value)]
    peripheral = ButtonPeripheral(parse_args(argv))
    peripheral.connect_if_needed(0)
    conn, _ = server.accept()
    conn.recv(1024)  # discard the initial connect-time reassertion of default state
    return peripheral, conn


def test_parse_args_rejects_same_bit_for_push_and_toggle():
    with pytest.raises(SystemExit):
        parse_args(["--push-bit", "3", "--toggle-bit", "3"])


def test_set_push_sends_bit_for_configured_pin(via_server):
    sock_path, server = via_server
    peripheral, conn = _make_peripheral(sock_path, server, push_bit=2, toggle_bit=5)

    peripheral.set_push(True)
    assert conn.recv(1024) == b"SA04"

    peripheral.set_push(False)
    assert conn.recv(1024) == b"RA04"

    peripheral.close()
    conn.close()


def test_set_push_is_a_noop_when_state_unchanged(via_server):
    sock_path, server = via_server
    peripheral, conn = _make_peripheral(sock_path, server, push_bit=0, toggle_bit=1)
    conn.setblocking(False)

    peripheral.set_push(False)  # already False: must send nothing
    with pytest.raises(BlockingIOError):
        conn.recv(1024)

    peripheral.close()
    conn.close()


def test_toggle_flips_state_and_sends_bit(via_server):
    sock_path, server = via_server
    peripheral, conn = _make_peripheral(sock_path, server, push_bit=2, toggle_bit=5)

    peripheral.toggle()
    assert peripheral.toggle_active is True
    assert conn.recv(1024) == b"SA20"

    peripheral.toggle()
    assert peripheral.toggle_active is False
    assert conn.recv(1024) == b"RA20"

    peripheral.close()
    conn.close()


def test_reconnect_reasserts_current_state(via_server):
    sock_path, server = via_server
    peripheral, conn = _make_peripheral(sock_path, server, push_bit=0, toggle_bit=1)

    peripheral.set_push(True)
    peripheral.toggle()
    assert conn.recv(1024) == b"SA01SA02"

    # Simulate a dropped connection.
    conn.close()
    peripheral.poll()
    assert not peripheral.connected

    peripheral.connect_if_needed(0)
    conn2, _ = server.accept()

    data = b""
    while len(data) < len(b"SA01SA02"):
        data += conn2.recv(1024)
    assert data == b"SA01SA02"

    peripheral.close()
    conn2.close()
