"""Tests for the reusable cell layout math (Cell/DataCell/ControlCell, layout_row).

Rendering itself (pygame.draw calls) is a manual-verification concern; these
tests cover the pure geometry that later units' visual fidelity depends on.
"""

from __future__ import annotations

from emma65_via_playground import cells


def make_data_cell(name="PA0"):
    return cells.DataCell(name, direction="in", local=True, pin=True)


def make_ctrl_cell(name="CA1"):
    return cells.ControlCell(name, direction="in", mode="pulse", polarity="rising")


def test_data_and_control_cell_widths_are_equal():
    # Checkpoint 2 equalized control-cell width to data-cell width -- the
    # only remaining visual cue between them is spacing (ctrl_group_gap).
    assert make_data_cell().width == cells.data_w
    assert make_ctrl_cell().width == cells.ctrl_w
    assert cells.data_w == cells.ctrl_w


def test_place_advances_by_width_plus_gap():
    cell = make_data_cell()
    next_x = cell.place(100)
    assert cell.rect.left == 100
    assert cell.rect.width == cells.data_w
    assert cell.rect.top == cells.row_y
    assert cell.rect.height == cells.cell_h
    assert next_x == 100 + cells.data_w + cells.gap


def test_layout_row_places_cells_left_to_right_without_group_gap_among_data_cells():
    row = [make_data_cell("PA1"), make_data_cell("PA0")]
    cells.layout_row(row, 0)
    assert row[0].rect.left == 0
    assert row[1].rect.left == cells.data_w + cells.gap


def test_layout_row_inserts_ctrl_group_gap_once_at_data_to_ctrl_boundary():
    row = [make_data_cell("PA1"), make_data_cell("PA0"), make_ctrl_cell("CA1"), make_ctrl_cell("CA2")]
    cells.layout_row(row, 0)

    pa0, ca1, ca2 = row[1], row[2], row[3]
    # extra ctrl_group_gap only between the last data cell and the first
    # control cell, not anywhere else in the row.
    assert ca1.rect.left == pa0.rect.right + cells.gap + cells.ctrl_group_gap
    assert ca2.rect.left == ca1.rect.right + cells.gap


def test_layout_row_returns_right_edge_of_last_cell():
    row = [make_data_cell("PA0")]
    right_edge = cells.layout_row(row, 0)
    assert right_edge == row[0].rect.right


def test_measuring_and_placing_pass_agree_on_content_width():
    # checkpoint 2's fix: measure at start_x=0, then place at start_x=LEFT_MARGIN,
    # via the same function -- so margins can't silently drift apart.
    measured_right = cells.layout_row(cells.build_port_a(), 0)
    placed = cells.build_port_a()
    placed_right = cells.layout_row(placed, cells.LEFT_MARGIN)
    assert placed_right == measured_right + cells.LEFT_MARGIN
    assert placed[0].rect.left == cells.LEFT_MARGIN


def test_build_port_a_pin_order_and_kinds():
    row = cells.build_port_a()
    names = [cell.name for cell in row]
    assert names == ["PA7", "PA6", "PA5", "PA4", "PA3", "PA2", "PA1", "PA0", "CA1", "CA2"]
    kinds = [cell.kind for cell in row]
    assert kinds == ["data"] * 8 + ["ctrl"] * 2


def test_data_cell_chevron_filled_reflects_pin_not_local():
    cell = cells.DataCell("PA5", direction="out", local=True, pin=False)
    assert cell._chevron_filled() is False


def test_data_cell_driven_reflects_local_when_momentary_not_held():
    assert cells.DataCell("PA0", direction="out", local=True, pin=True).driven is True
    assert cells.DataCell("PA0", direction="out", local=False, pin=False).driven is False


def test_data_cell_driven_is_inverted_while_momentary_held():
    # Pulled up + momentary pressed: LED must go from lit to unlit.
    cell = cells.DataCell("PA0", direction="out", local=True, pin=True, momentary_pressed=True)
    assert cell.driven is False
    # Pulled down + momentary pressed: LED must go from unlit to lit.
    cell = cells.DataCell("PA0", direction="out", local=False, pin=False, momentary_pressed=True)
    assert cell.driven is True


def test_control_cell_chevron_is_always_placeholder_outline():
    # Direction is context-dependent on live PCR state, not derived yet --
    # the chevron is a deliberate always-outlined placeholder (checkpoint 1).
    for mode in ("pulse", "level"):
        cell = cells.ControlCell("CA2", direction="out", mode=mode, polarity="falling")
        assert cell._chevron_filled() is False


def test_build_port_a_direction_follows_declared_mask():
    # Direction can't be read from the VIA (the peer protocol never conveys
    # DDR) -- it's a declared property of how the panel is wired, passed in
    # as a mask rather than derived from anything live.
    row = cells.build_port_a(direction_mask=0b00000101)  # PA0, PA2 out; rest in
    data_cells = {cell.name: cell for cell in row if cell.kind == "data"}
    assert data_cells["PA0"].direction == "out"
    assert data_cells["PA2"].direction == "out"
    assert data_cells["PA1"].direction == "in"
    assert data_cells["PA7"].direction == "in"


def test_build_port_a_data_cells_carry_their_bit_index():
    row = cells.build_port_a()
    for cell in row:
        if cell.kind == "data":
            assert cell.bit == int(cell.name.removeprefix("PA"))


def test_toggle_rect_and_momentary_rect_are_distinct_and_within_cell():
    cell = make_data_cell()
    cell.place(0)
    toggle_rect = cell.toggle_rect()
    momentary_rect = cell.momentary_rect()
    assert not toggle_rect.colliderect(momentary_rect)
    assert cell.rect.contains(toggle_rect)
    assert cell.rect.contains(momentary_rect)
    # Toggle sits above the momentary button, per the settled label -> chevron
    # -> LED -> toggle -> momentary stacking order.
    assert toggle_rect.centery < momentary_rect.centery


def test_toggle_and_momentary_rects_track_cell_placement():
    cell = make_data_cell()
    cell.place(40)
    assert cell.toggle_rect().centerx == cell.rect.centerx
    assert cell.momentary_rect().centerx == cell.rect.centerx


def test_control_cell_mode_polarity_momentary_rects_are_distinct_and_within_cell():
    cell = make_ctrl_cell()
    cell.place(0)
    mode_rect = cell.mode_rect()
    polarity_rect = cell.polarity_rect()
    momentary_rect = cell.momentary_rect()

    assert not mode_rect.colliderect(polarity_rect)
    assert not polarity_rect.colliderect(momentary_rect)
    assert cell.rect.contains(mode_rect)
    assert cell.rect.contains(polarity_rect)
    assert cell.rect.contains(momentary_rect)
    # mode -> polarity -> momentary, top to bottom, per the settled stacking order.
    assert mode_rect.centery < polarity_rect.centery < momentary_rect.centery


def test_control_cell_rects_track_cell_placement():
    cell = make_ctrl_cell()
    cell.place(40)
    assert cell.mode_rect().centerx == cell.rect.centerx
    assert cell.polarity_rect().centerx == cell.rect.centerx
    assert cell.momentary_rect().centerx == cell.rect.centerx


def test_build_port_a_control_cells_carry_their_ctrl_pin_number():
    row = cells.build_port_a()
    ctrl_cells = {cell.name: cell for cell in row if cell.kind == "ctrl"}
    assert ctrl_cells["CA1"].ctrl_pin == 1
    assert ctrl_cells["CA2"].ctrl_pin == 2


def test_build_port_a_cells_carry_port_letter():
    row = cells.build_port_a()
    assert all(cell.port == "A" for cell in row)


def test_build_port_b_pin_order_and_kinds():
    row = cells.build_port_b()
    names = [cell.name for cell in row]
    assert names == ["PB6", "PB5", "PB4", "PB3", "PB2", "PB1", "PB0", "CB1", "CB2"]
    kinds = [cell.kind for cell in row]
    assert kinds == ["data"] * 7 + ["ctrl"] * 2
    assert all(cell.port == "B" for cell in row)


def test_build_port_b_direction_follows_declared_mask():
    row = cells.build_port_b(direction_mask=0b000101)  # PB0, PB2 out; rest in
    data_cells = {cell.name: cell for cell in row if cell.kind == "data"}
    assert data_cells["PB0"].direction == "out"
    assert data_cells["PB2"].direction == "out"
    assert data_cells["PB1"].direction == "in"
    assert data_cells["PB5"].direction == "in"


def test_build_port_b_control_cells_carry_their_ctrl_pin_number():
    row = cells.build_port_b()
    ctrl_cells = {cell.name: cell for cell in row if cell.kind == "ctrl"}
    assert ctrl_cells["CB1"].ctrl_pin == 1
    assert ctrl_cells["CB2"].ctrl_pin == 2


def test_build_port_is_the_shared_constructor_behind_build_port_a_and_b():
    a_names = [cell.name for cell in cells.build_port_a(0xF0)]
    generic_a_names = [cell.name for cell in cells.build_port("A", 8, 0xF0)]
    assert a_names == generic_a_names

    # PB6 is layered on separately by build_port_b (see PB6Cell); the rest
    # of the row still comes straight from the shared build_port.
    b_names = [cell.name for cell in cells.build_port_b(0x38)][1:]
    generic_b_names = [cell.name for cell in cells.build_port("B", 6, 0x38)]
    assert b_names == generic_b_names


def test_build_port_b_pb6_direction_follows_declared_mask():
    row = cells.build_port_b(direction_mask=0b1000000)  # PB6 out; rest in
    data_cells = {cell.name: cell for cell in row if cell.kind == "data"}
    assert data_cells["PB6"].direction == "out"
    assert data_cells["PB0"].direction == "in"


def test_build_port_b_pb6_defaults_to_declared_pulse_counting():
    pb6 = cells.build_port_b()[0]
    assert isinstance(pb6, cells.PB6Cell)
    assert pb6.pulse_counting is True
    # Forced pulled up at construction -- not something a toggle click set.
    assert pb6.local is True


def test_build_port_b_pb6_pulse_counting_can_be_declared_off():
    pb6 = cells.build_port_b(pulse_counting=False)[0]
    assert pb6.pulse_counting is False
    assert pb6.local is False


def test_control_cell_chevron_carries_the_declared_marker():
    assert make_ctrl_cell()._chevron_declared() is True


def test_data_cell_chevron_does_not_carry_the_declared_marker():
    assert make_data_cell()._chevron_declared() is False


def test_pb6_cell_chevron_does_not_carry_the_declared_marker():
    # The declared/fixed ambiguity for PB6 is about its LED, not its
    # chevron -- direction/level there are still live, DDR-governed data.
    pb6 = cells.build_port_b()[0]
    assert pb6._chevron_declared() is False


def test_layout_ports_places_each_port_via_layout_row_with_a_port_gap_between():
    port_a = cells.build_port_a()
    port_b = cells.build_port_b()
    cells.layout_ports([port_a, port_b], 0)

    assert port_a[0].rect.left == 0
    last_a, first_b = port_a[-1], port_b[0]
    assert first_b.rect.left == last_a.rect.right + cells.gap + cells.PORT_GAP


def test_layout_ports_returns_right_edge_of_last_port():
    port_a = cells.build_port_a()
    port_b = cells.build_port_b()
    right_edge = cells.layout_ports([port_a, port_b], 0)
    assert right_edge == port_b[-1].rect.right


def test_layout_ports_measuring_and_placing_agree_on_content_width():
    measured_right = cells.layout_ports([cells.build_port_a(), cells.build_port_b()], 0)
    placed_ports = [cells.build_port_a(), cells.build_port_b()]
    placed_right = cells.layout_ports(placed_ports, cells.LEFT_MARGIN)
    assert placed_right == measured_right + cells.LEFT_MARGIN
    assert placed_ports[0][0].rect.left == cells.LEFT_MARGIN
