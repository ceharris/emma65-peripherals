"""Tests for Peripheral's connect/reconnect plumbing."""

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


def test_parse_args_defaults_socket():
    args = parse_args([])
    assert args.socket == "~/.emma/sock/via6522"


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
