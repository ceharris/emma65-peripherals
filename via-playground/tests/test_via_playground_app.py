"""Tests for Peripheral's connect/reconnect plumbing and live Port A pin tracking."""

from __future__ import annotations

import socket

import pytest

from emma65_via_playground.app import Peripheral, parse_args


@pytest.fixture
def via_server(tmp_path):
    """A listening Unix-domain socket standing in for the VIA transport."""
    sock_path = str(tmp_path / "via.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)
    yield sock_path, server
    server.close()


@pytest.fixture
def connected_peripheral(via_server):
    """A Peripheral connected to `via_server`, plus the accepted server-side connection."""
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path]))
    peripheral.connect_if_needed(0)
    conn, _ = server.accept()
    yield peripheral, conn
    peripheral.close()
    conn.close()


def test_parse_args_defaults_socket():
    args = parse_args([])
    assert args.socket == "~/.emma/sock/via6522"


def test_parse_args_defaults_pa_direction():
    args = parse_args([])
    assert args.pa_direction == 0xF0


def test_parse_args_accepts_hex_pa_direction():
    args = parse_args(["--pa-direction", "0f"])
    assert args.pa_direction == 0x0F


def test_parse_args_rejects_out_of_range_pa_direction():
    with pytest.raises(SystemExit):
        parse_args(["--pa-direction", "100"])


def test_parse_args_rejects_non_hex_pa_direction():
    with pytest.raises(SystemExit):
        parse_args(["--pa-direction", "zz"])


def test_port_a_level_starts_at_zero(connected_peripheral):
    peripheral, _ = connected_peripheral
    assert peripheral.port_a_level == 0


def test_port_state_event_sets_port_a_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"A55")
    peripheral.poll()
    assert peripheral.port_a_level == 0x55


def test_port_b_state_event_does_not_affect_port_a_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"BFF")
    peripheral.poll()
    assert peripheral.port_a_level == 0


def test_set_port_bits_ors_into_port_a_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"A0F")
    peripheral.poll()
    conn.sendall(b"SA30")
    peripheral.poll()
    assert peripheral.port_a_level == 0x3F


def test_reset_port_bits_clears_from_port_a_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"AFF")
    peripheral.poll()
    conn.sendall(b"RA0F")
    peripheral.poll()
    assert peripheral.port_a_level == 0xF0


def test_not_connected_before_socket_exists(tmp_path):
    peripheral = Peripheral(parse_args(["--socket", str(tmp_path / "missing.sock")]))
    peripheral.connect_if_needed(0)
    assert not peripheral.connected


def test_connects_once_socket_is_up(via_server):
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path]))

    peripheral.connect_if_needed(0)
    assert peripheral.connected
    conn, _ = server.accept()

    peripheral.close()
    conn.close()


def test_reconnect_after_dropped_connection(via_server):
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path]))

    peripheral.connect_if_needed(0)
    conn, _ = server.accept()

    conn.close()
    peripheral.poll()
    assert not peripheral.connected

    peripheral.connect_if_needed(0)
    conn2, _ = server.accept()
    assert peripheral.connected

    peripheral.close()
    conn2.close()


def test_reconnect_respects_backoff_interval(tmp_path):
    peripheral = Peripheral(parse_args(["--socket", str(tmp_path / "missing.sock")]))

    peripheral.connect_if_needed(0)
    assert not peripheral.connected

    # Still within the backoff window: no new attempt, still not connected.
    peripheral.connect_if_needed(500)
    assert not peripheral.connected
