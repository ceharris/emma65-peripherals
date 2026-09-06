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
