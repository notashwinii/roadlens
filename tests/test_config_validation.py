import pytest
from pydantic import ValidationError

from core.config_schema import ZoneConfig


def test_zone_rejects_invalid_normalized_coordinate():
    with pytest.raises(ValidationError):
        ZoneConfig(
            id="bad_zone",
            name="Bad Zone",
            type="detection_roi",
            shape="polygon",
            points_normalized=[
                (1.2, 0.5),
                (0.2, 0.2),
                (0.4, 0.4),
            ],
        )
