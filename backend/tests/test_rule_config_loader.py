from core.config_loader import load_config
from core.config_schema import ConditionPredicateConfig, ZoneEventPredicateConfig


def test_load_rules_from_sample_config():
    config = load_config("configs/sample_camera.yaml")

    assert len(config.conditions) == 3
    assert len(config.rules) == 3

    restricted_rule = next(
        rule for rule in config.rules if rule.id == "restricted_zone_entry"
    )

    assert restricted_rule.actions == [
        "create_violation_event",
        "capture_license_plate",
        "send_to_review",
    ]
    assert isinstance(restricted_rule.when.all[0], ZoneEventPredicateConfig)
    assert isinstance(restricted_rule.when.all[1], ConditionPredicateConfig)
