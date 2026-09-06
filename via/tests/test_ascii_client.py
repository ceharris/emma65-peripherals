"""Tests for the VIA ASCII wire client's send-side framing and connection handling."""

from __future__ import annotations

import socket

import pytest

from emma65_via.ascii_client import ViaAsciiClient
from emma65_via.protocol import CtrlPinSet, PortBitsSet, PortState


@pytest.fixture
def connected_pair(tmp_path):
    """A ViaAsciiClient connected to a real Unix-domain listening socket.

    Yields (client, server_conn) so tests can send from the client and assert
    on the bytes a real peer would receive.
    """
    sock_path = str(tmp_path / "via.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)

    client = ViaAsciiClient(sock_path)
    assert client.connect() is True
    conn, _ = server.accept()

    yield client, conn

    client.close()
    conn.close()
    server.close()


def test_connect_returns_false_when_socket_missing(tmp_path):
    client = ViaAsciiClient(str(tmp_path / "missing.sock"))
    assert client.connect() is False
    assert not client.connected


def test_set_bits_sends_S_message(connected_pair):
    client, conn = connected_pair
    client.set_bits("A", 0x05)
    assert conn.recv(1024) == b"SA05"


def test_reset_bits_sends_R_message(connected_pair):
    client, conn = connected_pair
    client.reset_bits("B", 0x80)
    assert conn.recv(1024) == b"RB80"


def test_drain_raises_connection_error_when_peer_closes(connected_pair):
    client, conn = connected_pair
    conn.close()
    with pytest.raises(ConnectionError):
        client.drain()
    assert not client.connected


def test_drain_is_a_noop_when_no_data_pending(connected_pair):
    client, _conn = connected_pair
    client.drain()  # must not raise
    assert client.connected


def test_poll_decodes_events_from_the_wire(connected_pair):
    client, conn = connected_pair
    conn.sendall(b"A55 SA03 SCB1 ")
    assert client.poll() == [
        PortState(port="A", level=0x55),
        PortBitsSet(port="A", mask=0x03),
        CtrlPinSet(port="B", pin=1),
    ]


def test_poll_returns_empty_list_when_no_data_pending(connected_pair):
    client, _conn = connected_pair
    assert client.poll() == []
    assert client.connected


def test_poll_raises_connection_error_when_peer_closes(connected_pair):
    client, conn = connected_pair
    conn.close()
    with pytest.raises(ConnectionError):
        client.poll()
    assert not client.connected


def test_poll_decoder_state_is_reset_on_reconnect(tmp_path):
    sock_path = str(tmp_path / "via.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)

    client = ViaAsciiClient(sock_path)
    assert client.connect() is True
    conn, _ = server.accept()

    # Leave a PortState message half-sent (port letter + high nibble only).
    conn.sendall(b"A5")
    assert client.poll() == []
    conn.close()
    client.close()

    assert client.connect() is True
    conn, _ = server.accept()
    # 'F' would complete the old message (as PortState A=0x5F) if decoder
    # state had leaked across the reconnect; a freshly-reset decoder just
    # discards it, since 'F' doesn't start any message on its own.
    conn.sendall(b"F")
    assert client.poll() == []

    client.close()
    conn.close()
    server.close()
