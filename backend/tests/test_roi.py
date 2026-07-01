from ingestion.roi import clamp_roi


def test_clamp_roi_clamps_negative_coordinates_to_frame_bounds():
    assert clamp_roi(-10, -20, 500, 500, 100, 80) == (0, 0, 100, 80)


def test_clamp_roi_clamps_oversized_roi_to_remaining_frame():
    assert clamp_roi(90, 70, 50, 50, 100, 80) == (90, 70, 10, 10)


def test_clamp_roi_preserves_valid_roi():
    assert clamp_roi(10, 20, 30, 40, 100, 100) == (10, 20, 30, 40)


def test_clamp_roi_enforces_minimum_size():
    assert clamp_roi(10, 20, 0, -5, 100, 100) == (10, 20, 1, 1)
