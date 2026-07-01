import numpy as np

from ingestion import video_feed
from ingestion.video_feed import _crop_with_rect, selected_frames


def test_crop_with_rect_uses_shared_roi_clipping():
    frame = np.zeros((80, 100, 3), dtype=np.uint8)

    crop, roi = _crop_with_rect(frame, (-10, 70, 200, 40))

    assert roi == (0, 70, 100, 10)
    assert crop.shape == (10, 100, 3)


def test_selected_frames_includes_metadata(monkeypatch):
    class FakeCap:
        def __init__(self):
            self.frames = [np.zeros((50, 60, 3), dtype=np.uint8)]

        def isOpened(self):
            return True

        def read(self):
            if self.frames:
                return True, self.frames.pop(0)
            return False, None

        def get(self, _property):
            return 10

    class FakeBackgroundSubtractor:
        def apply(self, frame):
            mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            mask[5:30, 5:30] = 255
            return mask

    monkeypatch.setattr(video_feed, "calculate_sharpness", lambda _frame: 2.0)
    monkeypatch.setattr(
        video_feed.cv2,
        "createBackgroundSubtractorMOG2",
        lambda **_kwargs: FakeBackgroundSubtractor(),
    )

    result = next(selected_frames(FakeCap(), roi=(0, 0, 60, 50)))

    assert result["frame_number"] == 0
    assert result["roi"] == (0, 0, 60, 50)
    assert result["selection_reason"] == "end_of_video"
    assert result["motion_area"] > 100
    assert result["sharpness"] == 2.0
    assert result["score"] == result["motion_area"] * result["sharpness"]
    assert result["timestamp_seconds"] == 0
