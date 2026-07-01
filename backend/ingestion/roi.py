def clamp_roi(
    x: int | float,
    y: int | float,
    width: int | float,
    height: int | float,
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, int, int]:
    x = max(0, min(int(x), frame_width - 1))
    y = max(0, min(int(y), frame_height - 1))
    width = max(1, min(int(width), frame_width - x))
    height = max(1, min(int(height), frame_height - y))
    return x, y, width, height


def clamp_roi_to_shape(
    roi: tuple[int | float, int | float, int | float, int | float],
    frame_shape: tuple[int, ...],
) -> tuple[int, int, int, int]:
    frame_height, frame_width = frame_shape[:2]
    return clamp_roi(*roi, frame_width, frame_height)
