"""Tests for Peripheral's connect/reconnect plumbing and live port pin tracking."""

from __future__ import annotations

import socket
import threading
import time

import pytest

import numpy as np

from emma65_via_playground import app
from emma65_via_playground.app import (
    CTRL_PULSE_DURATION_MS,
    PB7_AUDIO_AMPLITUDE,
    ControlPinState,
    Pb7Audio,
    Peripheral,
    PortIO,
    PB7State,
    parse_args,
)


@pytest.fixture(autouse=True)
def _no_real_audio_hardware(monkeypatch):
    """Force Pb7Audio's no-PortAudio degrade path for every test in this module.

    Every `Peripheral()` construction builds a real `Pb7Audio`, which opens
    an actual hardware audio stream whenever PortAudio happens to be
    installed on the machine running the tests -- not hermetic, and
    genuinely hangs after enough rapid open/close cycles across dozens of
    tests (observed directly: this suite wedged the moment `libportaudio2`
    got installed on a dev machine that previously lacked it, with no
    change to the test code itself). No test in this file needs a real
    stream -- Pb7Audio-specific tests below exercise `_callback`/
    `_read_loop` directly -- so unconditionally patching `sd` to `None`
    here restores the rest of the suite to being independent of whatever
    audio hardware/drivers happen to be present.
    """
    monkeypatch.setattr(app, "sd", None)


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


def test_parse_args_defaults_pb_direction():
    args = parse_args([])
    assert args.pb_direction == 0xB8


def test_parse_args_accepts_hex_pb_direction():
    args = parse_args(["--pb-direction", "3f"])
    assert args.pb_direction == 0x3F


def test_parse_args_defaults_pb6_pulse_counting_on():
    args = parse_args([])
    assert args.pb6_pulse_counting is True


def test_parse_args_accepts_disabling_pb6_pulse_counting():
    args = parse_args(["--no-pb6-pulse-counting"])
    assert args.pb6_pulse_counting is False


def test_parse_args_defaults_pb7_free_run_off():
    args = parse_args([])
    assert args.pb7_free_run is False


def test_parse_args_accepts_enabling_pb7_free_run():
    args = parse_args(["--pb7-free-run"])
    assert args.pb7_free_run is True


def test_port_levels_start_at_zero(connected_peripheral):
    peripheral, _ = connected_peripheral
    assert peripheral.ports["A"].level == 0
    assert peripheral.ports["B"].level == 0


def test_port_state_event_sets_that_ports_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"A55")
    peripheral.poll()
    assert peripheral.ports["A"].level == 0x55
    assert peripheral.ports["B"].level == 0


def test_port_b_state_event_does_not_affect_port_a_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"BFF")
    peripheral.poll()
    assert peripheral.ports["A"].level == 0
    assert peripheral.ports["B"].level == 0xFF


def test_set_port_bits_ors_into_that_ports_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"A0F")
    peripheral.poll()
    conn.sendall(b"SA30")
    peripheral.poll()
    assert peripheral.ports["A"].level == 0x3F


def test_reset_port_bits_clears_from_that_ports_level(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.sendall(b"AFF")
    peripheral.poll()
    conn.sendall(b"RA0F")
    peripheral.poll()
    assert peripheral.ports["A"].level == 0xF0


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


def test_toggle_data_flips_local_state_and_sends_bit(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_data("A", 3)
    assert peripheral.ports["A"].local == 0x08
    assert conn.recv(1024) == b"SA08"

    peripheral.toggle_data("A", 3)
    assert peripheral.ports["A"].local == 0x00
    assert conn.recv(1024) == b"RA08"

    peripheral.close()
    conn.close()


def test_toggle_data_only_touches_its_own_bit(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_data("A", 0)
    conn.recv(1024)
    peripheral.toggle_data("A", 5)
    assert conn.recv(1024) == b"SA20"
    assert peripheral.ports["A"].local == 0x21


def test_toggle_data_on_port_b_uses_port_b_wire_messages(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_data("B", 2)
    # Bit 6 is already forced high by PB6's declared pulse-counting default.
    assert peripheral.ports["B"].local == 0x44
    assert conn.recv(1024) == b"SB04"
    assert peripheral.ports["A"].local == 0  # Port A untouched

    peripheral.close()
    conn.close()


def test_momentary_press_asserts_opposite_of_toggle_level(connected_peripheral):
    peripheral, conn = connected_peripheral

    # Toggle off (local low): momentary press should drive high.
    peripheral.set_momentary("A", 2, True)
    assert conn.recv(1024) == b"SA04"

    # Release: back to the toggle's (low) level.
    peripheral.set_momentary("A", 2, False)
    assert conn.recv(1024) == b"RA04"

    peripheral.close()
    conn.close()


def test_momentary_press_with_toggle_on_asserts_low(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_data("A", 4)
    assert conn.recv(1024) == b"SA10"

    peripheral.set_momentary("A", 4, True)
    assert conn.recv(1024) == b"RA10"

    peripheral.set_momentary("A", 4, False)
    assert conn.recv(1024) == b"SA10"

    peripheral.close()
    conn.close()


def test_momentary_is_a_noop_when_state_unchanged(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.setblocking(False)

    peripheral.set_momentary("A", 1, False)  # already released: must send nothing
    with pytest.raises(BlockingIOError):
        conn.recv(1024)

    peripheral.close()
    conn.close()


def test_reconnect_reasserts_local_and_momentary_state_for_all_owned_bits(via_server):
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path]))

    peripheral.connect_if_needed(0)
    conn, _ = server.accept()
    conn.recv(1024)  # discard the initial connect-time reassertion (all bits low)

    peripheral.toggle_data("A", 1)
    peripheral.toggle_data("A", 6)
    peripheral.set_momentary("A", 6, True)  # overrides bit 6 back to low
    peripheral.toggle_data("B", 2)
    conn.recv(1024)  # discard those interaction messages

    conn.close()
    peripheral.poll()
    assert not peripheral.connected

    peripheral.connect_if_needed(0)
    conn2, _ = server.accept()

    # Reassertion happens per port (all of a port's bits, then its two
    # control pins, before moving to the next port). Port A: bit 1's toggle
    # is on (driven high); bit 6's toggle is also on, but its momentary
    # press overrides it back to driven-low; every other bit is driven low
    # by its (untouched) toggle position; CA1/CA2 are untouched, so they
    # reassert to their default (rising) polarity's idle-low level. Port B:
    # bit 2 is on, bit 6 (PB6) is forced high by its declared pulse-counting
    # default, every other owned bit (0,1,3,4,5,7 -- PB7's toggle is
    # untouched, ordinary low) is driven low; CB1/CB2 are likewise
    # untouched.
    expected = (
        b"".join(b"SA02" if bit == 1 else b"RA%02X" % (1 << bit) for bit in range(8))
        + b"RCA1RCA2"
        + b"".join(
            b"SB04" if bit == 2 else b"SB40" if bit == 6 else b"RB%02X" % (1 << bit)
            for bit in range(8)
        )
        + b"RCB1RCB2"
    )
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

    peripheral.press_ctrl("A", 1, 0)  # CA1 default: level mode, rising polarity (idle low)
    assert conn.recv(1024) == b"SCA1"

    peripheral.release_ctrl("A", 1)
    assert conn.recv(1024) == b"RCA1"

    peripheral.close()
    conn.close()


def test_press_ctrl_on_port_b_uses_port_b_wire_messages(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.press_ctrl("B", 1, 0)
    assert conn.recv(1024) == b"SCB1"

    peripheral.release_ctrl("B", 1)
    assert conn.recv(1024) == b"RCB1"

    peripheral.close()
    conn.close()


def test_press_ctrl_in_level_mode_respects_falling_polarity(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_polarity("A", 2)  # CA2 default is rising (idle low); flip to falling
    assert conn.recv(1024) == b"SCA2"  # idle level flips high, so it re-asserts immediately

    peripheral.press_ctrl("A", 2, 0)
    assert conn.recv(1024) == b"RCA2"  # falling polarity's active level is low

    peripheral.close()
    conn.close()


def test_press_ctrl_in_pulse_mode_fires_one_transition_ignoring_hold_time(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_mode("A", 1)  # CA1 -> pulse mode
    peripheral.press_ctrl("A", 1, 1000)
    assert conn.recv(1024) == b"SCA1"

    # Releasing before the pulse duration elapses must not change the wire.
    peripheral.release_ctrl("A", 1)
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

    peripheral.toggle_ctrl_mode("A", 1)
    peripheral.press_ctrl("A", 1, 1000)
    conn.recv(1024)

    peripheral.press_ctrl("A", 1, 1050)  # re-press before the first pulse would have ended
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


def test_update_ctrl_pulses_reverts_independently_per_port(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_mode("A", 1)
    peripheral.toggle_ctrl_mode("B", 1)
    peripheral.press_ctrl("A", 1, 1000)
    peripheral.press_ctrl("B", 1, 1000)
    conn.recv(1024)  # discard both presses (SCA1, SCB1, order not asserted)

    peripheral.update_ctrl_pulses(1000 + CTRL_PULSE_DURATION_MS)
    data = conn.recv(1024)
    assert b"RCA1" in data
    assert b"RCB1" in data

    peripheral.close()
    conn.close()


def test_toggle_ctrl_mode_cancels_an_in_flight_pulse(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_ctrl_mode("A", 1)  # -> pulse
    peripheral.press_ctrl("A", 1, 1000)
    conn.recv(1024)

    peripheral.toggle_ctrl_mode("A", 1)  # -> level, mid-pulse
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

    peripheral.toggle_ctrl_mode("A", 1)  # CA1 -> pulse
    peripheral.press_ctrl("A", 1, 0)  # begin a pulse, currently driving active-high
    conn.recv(1024)

    conn.close()
    peripheral.poll()
    assert not peripheral.connected

    peripheral.connect_if_needed(0)
    conn2, _ = server.accept()

    # Reassertion happens per port. CA1's pulse is still "in flight" per its
    # own state (reconnecting doesn't cancel it) so it reasserts the active
    # level; every other control pin (CA2, CB1, CB2) is untouched and
    # reasserts its idle (rising-polarity, idle-low) level. Port B's bit 6
    # (PB6) is forced high by its declared pulse-counting default; every
    # other owned bit, including PB7, is an untouched, ordinary low toggle.
    expected = (
        b"".join(b"RA%02X" % (1 << bit) for bit in range(8))
        + b"SCA1RCA2"
        + b"".join(b"SB40" if bit == 6 else b"RB%02X" % (1 << bit) for bit in range(8))
        + b"RCB1RCB2"
    )
    data = b""
    while len(data) < len(expected):
        data += conn2.recv(1024)
    assert data == expected

    peripheral.close()
    conn2.close()


def test_pb6_starts_forced_pulled_up_when_pulse_counting_declared(connected_peripheral):
    peripheral, _ = connected_peripheral
    assert peripheral.ports["B"].local & 0x40


def test_pb6_stays_ordinary_data_bit_when_pulse_counting_declared_off(via_server):
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path, "--no-pb6-pulse-counting"]))
    peripheral.connect_if_needed(0)
    server.accept()
    assert peripheral.ports["B"].local & 0x40 == 0
    peripheral.close()


def test_press_pb6_in_level_mode_drives_low_while_held(connected_peripheral):
    peripheral, conn = connected_peripheral

    # Idle is forced pulled up; a level-mode press pulls the line low.
    peripheral.press_pb6("B", 0)
    assert conn.recv(1024) == b"RB40"

    peripheral.release_pb6("B")
    assert conn.recv(1024) == b"SB40"

    peripheral.close()
    conn.close()


def test_toggle_pb6_mode_flips_between_level_and_pulse(connected_peripheral):
    peripheral, _ = connected_peripheral

    assert peripheral.ports["B"].pb6.mode == "level"
    peripheral.toggle_pb6_mode("B")
    assert peripheral.ports["B"].pb6.mode == "pulse"
    peripheral.toggle_pb6_mode("B")
    assert peripheral.ports["B"].pb6.mode == "level"


def test_press_pb6_in_pulse_mode_fires_one_transition_ignoring_hold_time(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_pb6_mode("B")  # -> pulse
    peripheral.press_pb6("B", 1000)
    assert conn.recv(1024) == b"RB40"

    # Releasing before the pulse duration elapses must not change the wire.
    peripheral.release_pb6("B")
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
    assert conn.recv(1024) == b"SB40"

    peripheral.close()
    conn.close()


def test_pressing_pb6_again_mid_pulse_restarts_the_timer(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_pb6_mode("B")
    peripheral.press_pb6("B", 1000)
    conn.recv(1024)

    peripheral.press_pb6("B", 1050)  # re-press before the first pulse would have ended
    conn.recv(1024)  # re-asserts the active (low) level again

    # The original deadline (1000 + duration) has passed, but the restarted
    # one (1050 + duration) has not -- must not have reverted yet.
    peripheral.update_ctrl_pulses(1000 + CTRL_PULSE_DURATION_MS)
    conn.setblocking(False)
    with pytest.raises(BlockingIOError):
        conn.recv(1024)
    conn.setblocking(True)

    peripheral.update_ctrl_pulses(1050 + CTRL_PULSE_DURATION_MS)
    assert conn.recv(1024) == b"SB40"

    peripheral.close()
    conn.close()


def test_pb7_uses_ordinary_toggle_and_momentary_wire_behavior(connected_peripheral):
    # Unlike PB6, PB7's toggle/momentary are never repurposed -- bit 7
    # behaves exactly like any other Port B data bit.
    peripheral, conn = connected_peripheral

    peripheral.toggle_data("B", 7)
    assert peripheral.ports["B"].local & 0x80
    assert conn.recv(1024) == b"SB80"

    peripheral.set_momentary("B", 7, True)
    assert conn.recv(1024) == b"RB80"

    peripheral.close()
    conn.close()


def test_toggle_pb7_speaker_flips_local_state_without_touching_the_wire(connected_peripheral):
    peripheral, conn = connected_peripheral
    conn.setblocking(False)

    assert peripheral.ports["B"].pb7.speaker_on is True
    peripheral.toggle_pb7_speaker("B")
    assert peripheral.ports["B"].pb7.speaker_on is False
    peripheral.toggle_pb7_speaker("B")
    assert peripheral.ports["B"].pb7.speaker_on is True

    with pytest.raises(BlockingIOError):
        conn.recv(1024)

    peripheral.close()
    conn.close()


def test_pb7_free_run_declaration_does_not_affect_local_state(via_server):
    sock_path, server = via_server
    peripheral = Peripheral(parse_args(["--socket", sock_path, "--pb7-free-run"]))
    peripheral.connect_if_needed(0)
    server.accept()
    assert peripheral.ports["B"].pb7.free_run is True
    assert peripheral.ports["B"].local & 0x80 == 0  # PB7's toggle is untouched, ordinary low
    peripheral.close()


def test_pb7_audio_degrades_gracefully_without_portaudio():
    # sd is forced to None module-wide (see _no_real_audio_hardware) -- this
    # exercises the real degrade path, not just a mock. The reader thread
    # must never start either, since sd is None short-circuits __init__
    # before it's spawned.
    audio = Pb7Audio(PortIO(pb7=PB7State(free_run=False)), "/nonexistent")
    assert audio._reader_thread is None
    audio.close()  # must not raise even though no stream/thread was ever started


def test_pb7_audio_callback_outputs_positive_amplitude_when_bit_high_and_routed(monkeypatch):
    # A controllable fake clock lets the test move past the jitter-buffer
    # delay deterministically instead of racing a real one.
    fake_time = [0.0]
    monkeypatch.setattr(app.time, "perf_counter", lambda: fake_time[0])

    port_b = PortIO(pb7=PB7State(free_run=False, speaker_on=True))
    audio = Pb7Audio(port_b, "/nonexistent")
    audio._on_edge(True, fake_time[0])
    fake_time[0] += 0.020  # past PB7_AUDIO_JITTER_MS (15ms), so the read position has caught up

    outdata = np.zeros((4, 1), dtype="float32")
    audio._callback(outdata, 4, None, None)
    assert (outdata[:, 0] == PB7_AUDIO_AMPLITUDE).all()


def test_pb7_audio_callback_outputs_negative_amplitude_when_bit_low_and_routed(monkeypatch):
    fake_time = [0.0]
    monkeypatch.setattr(app.time, "perf_counter", lambda: fake_time[0])

    port_b = PortIO(pb7=PB7State(free_run=False, speaker_on=True))
    audio = Pb7Audio(port_b, "/nonexistent")
    audio._on_edge(False, fake_time[0])
    fake_time[0] += 0.020

    outdata = np.zeros((4, 1), dtype="float32")
    audio._callback(outdata, 4, None, None)
    assert (outdata[:, 0] == -PB7_AUDIO_AMPLITUDE).all()


def test_pb7_audio_callback_is_silent_when_not_routed(monkeypatch):
    fake_time = [0.0]
    monkeypatch.setattr(app.time, "perf_counter", lambda: fake_time[0])

    port_b = PortIO(pb7=PB7State(free_run=False, speaker_on=False))
    audio = Pb7Audio(port_b, "/nonexistent")
    audio._on_edge(True, fake_time[0])
    fake_time[0] += 0.020

    outdata = np.zeros((4, 1), dtype="float32")
    audio._callback(outdata, 4, None, None)
    assert (outdata[:, 0] == 0.0).all()


def test_pb7_audio_callback_is_silent_before_the_first_edge():
    # _t0 is None until the reader thread observes a first transition --
    # the callback must not divide by/index against an origin that doesn't
    # exist yet.
    port_b = PortIO(pb7=PB7State(free_run=False, speaker_on=True))
    audio = Pb7Audio(port_b, "/nonexistent")
    outdata = np.full((4, 1), 1.0, dtype="float32")
    audio._callback(outdata, 4, None, None)
    assert (outdata[:, 0] == 0.0).all()


def test_pb7_audio_reader_loop_tracks_bit7_via_its_own_dedicated_connection(via_server):
    # This exercises _read_loop directly (bypassing the sd-is-None gate in
    # __init__, forced by _no_real_audio_hardware) against a second,
    # independent fake-VIA connection -- proving the dedicated-connection
    # design actually works, not just that _on_edge's/_callback's
    # arithmetic is right in isolation.
    sock_path, server = via_server
    port_b = PortIO(pb7=PB7State(free_run=False, speaker_on=True))
    audio = Pb7Audio(port_b, sock_path)
    reader = threading.Thread(target=audio._read_loop, daemon=True)
    reader.start()
    conn, _ = server.accept()

    def wait_for(predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.001)
        return False

    conn.sendall(b"B80")  # PortState: Port B = 0x80, bit 7 high
    assert wait_for(lambda: audio._level == PB7_AUDIO_AMPLITUDE)

    conn.sendall(b"RB80")  # PortBitsReset: bit 7 low
    assert wait_for(lambda: audio._level == -PB7_AUDIO_AMPLITUDE)

    conn.sendall(b"SB80")  # PortBitsSet: bit 7 high again
    assert wait_for(lambda: audio._level == PB7_AUDIO_AMPLITUDE)

    audio._stop.set()
    reader.join(timeout=1.0)
    assert not reader.is_alive()
    conn.close()


def test_pb7_audio_render_to_paints_ring_with_current_level():
    audio = Pb7Audio(PortIO(pb7=PB7State(free_run=False)), "/nonexistent")
    audio._level = PB7_AUDIO_AMPLITUDE
    with audio._lock:
        audio._render_to(10)
    assert (audio._ring[:10] == PB7_AUDIO_AMPLITUDE).all()
    assert audio._write_pos == 10


def test_pb7_audio_render_to_is_a_noop_when_target_not_ahead():
    audio = Pb7Audio(PortIO(pb7=PB7State(free_run=False)), "/nonexistent")
    with audio._lock:
        audio._render_to(10)
        audio._level = PB7_AUDIO_AMPLITUDE
        audio._render_to(5)  # behind the current write position -- must not repaint backwards
    assert audio._write_pos == 10
    assert (audio._ring[:10] == -PB7_AUDIO_AMPLITUDE).all()  # untouched by the no-op call


def test_pb7_audio_render_to_catches_up_when_hopelessly_behind():
    audio = Pb7Audio(PortIO(pb7=PB7State(free_run=False)), "/nonexistent")
    huge_target = app.PB7_AUDIO_RING_CAPACITY * 3
    with audio._lock:
        audio._level = PB7_AUDIO_AMPLITUDE
        audio._render_to(huge_target)
    assert audio._write_pos == huge_target
    assert (audio._ring == PB7_AUDIO_AMPLITUDE).all()


def test_toggle_pb6_mode_cancels_an_in_flight_pulse(connected_peripheral):
    peripheral, conn = connected_peripheral

    peripheral.toggle_pb6_mode("B")  # -> pulse
    peripheral.press_pb6("B", 1000)
    conn.recv(1024)

    peripheral.toggle_pb6_mode("B")  # -> level, mid-pulse
    assert conn.recv(1024) == b"SB40"  # reverted to idle (pulled-up) immediately

    # The cancelled pulse's deadline must no longer fire a spurious revert.
    peripheral.update_ctrl_pulses(1000 + CTRL_PULSE_DURATION_MS)
    conn.setblocking(False)
    with pytest.raises(BlockingIOError):
        conn.recv(1024)
    conn.setblocking(True)

    peripheral.close()
    conn.close()
