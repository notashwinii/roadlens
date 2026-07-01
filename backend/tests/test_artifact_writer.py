import numpy as np

from evidence.artifact_writer import write_image_artifact


def test_write_image_artifact(tmp_path):
    image = np.zeros((20, 40, 3), dtype=np.uint8)

    path, width, height = write_image_artifact(
        image,
        output_dir=str(tmp_path),
        camera_id="camera_1",
        video_id=1,
        event_id=2,
        artifact_type="plate_crop",
    )

    assert width == 40
    assert height == 20
    assert path.endswith("camera_1/video_000001/event_000002/plate_crop.jpg")
    assert (tmp_path / "camera_1/video_000001/event_000002/plate_crop.jpg").exists()
