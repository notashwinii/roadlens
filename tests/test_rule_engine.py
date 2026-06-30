from core.config_schema import (
    ConditionConfig,
    ConditionPredicateConfig,
    RuleConfig,
    RuleWhenConfig,
    ZoneEventPredicateConfig,
)
from rules.conditions import ConditionProvider
from rules.events import VehicleZoneEvent
from rules.rule_engine import RuleEngine


def test_restricted_zone_rule_matches_event():
    condition_provider = ConditionProvider(
        [
            ConditionConfig(
                id="always_forbidden",
                name="Always Forbidden",
                type="always_true",
            )
        ]
    )
    rule = RuleConfig(
        id="restricted_zone_entry",
        name="Restricted Zone Entry",
        enabled=True,
        when=RuleWhenConfig(
            all=[
                ZoneEventPredicateConfig(
                    event="vehicle_intersects_zone",
                    zone_type="restricted_zone",
                ),
                ConditionPredicateConfig(condition="always_forbidden"),
            ]
        ),
        actions=["create_violation_event", "capture_license_plate"],
    )
    event = VehicleZoneEvent(
        event="vehicle_intersects_zone",
        frame_number=10,
        timestamp_seconds=0.33,
        vehicle_index=1,
        vehicle_class="car",
        vehicle_confidence=0.9,
        vehicle_bbox=(10, 10, 50, 50),
        zone_id="restricted_lane_left",
        zone_type="restricted_zone",
        zone_name="Restricted Left Lane",
    )

    engine = RuleEngine([rule], condition_provider)

    matches = engine.matching_rules(event)

    assert len(matches) == 1
    assert matches[0].id == "restricted_zone_entry"


def test_rule_does_not_match_missing_condition():
    rule = RuleConfig(
        id="restricted_zone_entry",
        name="Restricted Zone Entry",
        enabled=True,
        when=RuleWhenConfig(
            all=[
                ZoneEventPredicateConfig(
                    event="vehicle_intersects_zone",
                    zone_type="restricted_zone",
                ),
                ConditionPredicateConfig(condition="missing_condition"),
            ]
        ),
        actions=["create_violation_event"],
    )
    event = VehicleZoneEvent(
        event="vehicle_intersects_zone",
        frame_number=10,
        timestamp_seconds=0.33,
        vehicle_index=1,
        vehicle_class="car",
        vehicle_confidence=0.9,
        vehicle_bbox=(10, 10, 50, 50),
        zone_id="restricted_lane_left",
        zone_type="restricted_zone",
        zone_name="Restricted Left Lane",
    )

    engine = RuleEngine([rule], ConditionProvider([]))

    assert engine.matching_rules(event) == []
