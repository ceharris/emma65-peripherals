"""Tests for Peripheral's connect/reconnect plumbing and live Port A pin tracking."""

from __future__ import annotations

import socket

import pytest

from emma65_via_playground.app import CTRL_PULSE_DURATION_MS, ControlPinState, Peripheral, parse_args


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
    conn.recv(1024)  # discard the initial connect-time reassertion of default data/control state
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


def test_toggle_pa_flips_local_state_and_sends_bit(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_pa(3)
    assert peripheral.pa_local == 0x08
    assert conn.recv(1024) == b"SA08"

    peripheral.toggle_pa(3)
    assert peripheral.pa_local == 0x00
    assert conn.recv(1024) == b"RA08"

    peripheral.close()
    conn.close()


def test_toggle_pa_only_touches_its_own_bit(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_pa(0)
    conn.recv(1024)
    peripheral.toggle_pa(5)
    assert conn.recv(1024) == b"SA20"
    assert peripheral.pa_local == 0x21

    peripheral.close()
    conn.close()


def test_momentary_press_asserts_opposite_of_toggle_level(connected_peripheral):
    peripheral, conn = connected_peripheral

    # Toggle off (local low): momentary press should drive high.
    peripheral.set_pa_momentary(2, True)
    assert conn.recv(1024) == b"SA04"

    # Release: back to the toggle's (low) level.
    peripheral.set_pa_momentary(2, False)
    assert conn.recv(1024) == b"RA04"

    peripheral.close()
    conn.close()


def test_momentary_press_with_toggle_on_asserts_low(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_pa(4)
    assert conn.recv(1024) == b"SA10"

    peripheral.set_pa_momentary(4, True)
    assert conn.recv(1024) == b"RA10"

    peripheral.set_pa_momentary(4, False)
    assert conn.recv(1024) == b"SA10"

    peripheral.close()
    conn.close()


def test_momentary_is_a_noop_when_state_unchanged(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.setblocking(False)

    peripheral.set_pa_momentary(1, False)  # already released: must send nothing
    with pytest.raises(BlockingIOError):
        conn.recv(1024)

    peripheral.close()
    conn.close()


def test_reconnect_reasserts_local_and_momentary_state_for_all_bits(via_server):
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path]))

    peripheral.connect_if_needed(0)
    conn, _ = server.accept()
    conn.recv(1024)  # discard the initial connect-time reassertion (all bits low)

    peripheral.toggle_pa(1)
    peripheral.toggle_pa(6)
    peripheral.set_pa_momentary(6, True)  # overrides bit 6 back to low
    conn.recv(1024)  # discard those three interaction messages

    conn.close()
    peripheral.poll()
    assert not peripheral.connected

    peripheral.connect_if_needed(0)
    conn2, _ = server.accept()

    # Bit 1's toggle is on (driven high); bit 6's toggle is also on, but its
    # momentary press overrides it back to driven-low; every other bit is
    # driven low by its (untouched) toggle position. CA1/CA2 are untouched,
    # so they reassert to their default (rising) polarity's idle-low level.
    expected = b"".join(
        b"SA02" if bit == 1 else b"RA%02X" % (1 << bit) for bit in range(8)
    ) + b"RCA1RCA2"
    data = b""
    while len(data) < len(expected):
        data += conn2.recv(1024)
    assert data == expected

    peripheral.close()
    conn2.close()


def test_control_pin_state_idle_level_follows_polarity():
    assert ControlPinState(polarity="rising").idle_level() is False
    assert ControlPinState(polarity="falling").idle_level() is True


def test_control_pin_state_driven_level_is_idle_when_untouched():
    state = ControlPinState(polarity="rising")
    assert state.driven_level() is False


def test_control_pin_state_driven_level_in_level_mode_while_held():
    state = ControlPinState(mode="level", polarity="rising", held=True)
    assert state.driven_level() is True  # active = opposite of idle


def test_control_pin_state_driven_level_while_pulsing_regardless_of_held():
    state = ControlPinState(mode="pulse", polarity="falling", held=False, pulse_release_at=500)
    assert state.driven_level() is False  # active = opposite of falling's idle-high


def test_press_ctrl_in_level_mode_drives_active_level_while_held(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.press_ctrl(1, 0)  # CA1 default: level mode, rising polarity (idle low)
    assert conn.recv(1024) == b"SCA1"

    peripheral.release_ctrl(1)
    assert conn.recv(1024) == b"RCA1"

    peripheral.close()
    conn.close()


def test_press_ctrl_in_level_mode_respects_falling_polarity(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_polarity(2)  # CA2 default is rising (idle low); flip to falling
    assert conn.recv(1024) == b"SCA2"  # idle level flips high, so it re-asserts immediately

    peripheral.press_ctrl(2, 0)
    assert conn.recv(1024) == b"RCA2"  # falling polarity's active level is low

    peripheral.close()
    conn.close()


def test_press_ctrl_in_pulse_mode_fires_one_transition_ignoring_hold_time(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_mode(1)  # CA1 -> pulse mode
    peripheral.press_ctrl(1, 1000)
    assert conn.recv(1024) == b"SCA1"

    # Releasing before the pulse duration elapses must not change the wire.
    peripheral.release_ctrl(1)
    conn.setblocking(False)
    with pytest.raises(BlockingIOError):
        conn.recv(1024)
    conn.setblocking(True)

    # Only update_ctrl_pulses, once the duration has elapsed, reverts to idle.
    peripheral.update_ctrl_pulses(1000 + CTRL_PULSE_DURATION_MS - 1)
    conn.setblocking(False)
    with pytest.raises(BlockingIOError):
        conn.recv(1024)
    conn.setblocking(True)

    peripheral.update_ctrl_pulses(1000 + CTRL_PULSE_DURATION_MS)
    assert conn.recv(1024) == b"RCA1"

    peripheral.close()
    conn.close()


def test_pressing_again_mid_pulse_restarts_the_timer(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_mode(1)
    peripheral.press_ctrl(1, 1000)
    conn.recv(1024)

    peripheral.press_ctrl(1, 1050)  # re-press before the first pulse would have ended
    conn.recv(1024)  # re-asserts the active level again

    # The original deadline (1000 + duration) has passed, but the restarted
    # one (1050 + duration) has not -- must not have reverted yet.
    peripheral.update_ctrl_pulses(1000 + CTRL_PULSE_DURATION_MS)
    conn.setblocking(False)
    with pytest.raises(BlockingIOError):
        conn.recv(1024)
    conn.setblocking(True)

    peripheral.update_ctrl_pulses(1050 + CTRL_PULSE_DURATION_MS)
    assert conn.recv(1024) == b"RCA1"

    peripheral.close()
    conn.close()


def test_toggle_ctrl_mode_cancels_an_in_flight_pulse(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_mode(1)  # -> pulse
    peripheral.press_ctrl(1, 1000)
    conn.recv(1024)

    peripheral.toggle_ctrl_mode(1)  # -> level, mid-pulse
    assert conn.recv(1024) == b"RCA1"  # reverted to idle immediately

    # The cancelled pulse's deadline must no longer fire a spurious revert.
    peripheral.update_ctrl_pulses(1000 + CTRL_PULSE_DURATION_MS)
    conn.setblocking(False)
    with pytest.raises(BlockingIOError):
        conn.recv(1024)
    conn.setblocking(True)

    peripheral.close()
    conn.close()


def test_reconnect_reasserts_control_pin_state(via_server):
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path]))

    peripheral.connect_if_needed(0)
    conn, _ = server.accept()
    conn.recv(1024)  # discard the initial connect-time reassertion

    peripheral.toggle_ctrl_mode(1)  # CA1 -> pulse
    peripheral.press_ctrl(1, 0)  # begin a pulse, currently driving active-high
    conn.recv(1024)

    conn.close()
    peripheral.poll()
    assert not peripheral.connected

    peripheral.connect_if_needed(0)
    conn2, _ = server.accept()

    # CA1's pulse is still "in flight" per its own state (reconnecting
    # doesn't cancel it) so it reasserts the active level; CA2 is untouched
    # and reasserts its idle (rising-polarity, idle-low) level.
    expected = b"".join(b"RA%02X" % (1 << bit) for bit in range(8)) + b"SCA1RCA2"
    data = b""
    while len(data) < len(expected):
        data += conn2.recv(1024)
    assert data == expected

    peripheral.close()
    conn2.close()
