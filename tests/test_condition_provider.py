from core.config_schema import ConditionConfig
from rules.conditions import ConditionProvider


def test_always_true_condition_is_active():
    provider = ConditionProvider(
        [
            ConditionConfig(
                id="always_forbidden",
                name="Always Forbidden",
                type="always_true",
            )
        ]
    )

    assert provider.is_active("always_forbidden") is True


def test_enabled_manual_state_condition_is_active():
    provider = ConditionProvider(
        [
            ConditionConfig(
                id="red_light_main",
                name="Main Signal Red Phase",
                type="manual_state",
                key="traffic_light_main",
                value="red",
            )
        ]
    )

    assert provider.is_active("red_light_main") is True


def test_missing_condition_is_inactive():
    provider = ConditionProvider([])

    assert provider.is_active("missing") is False


def test_disabled_condition_is_inactive():
    provider = ConditionProvider(
        [
            ConditionConfig(
                id="pedestrian_phase_main",
                name="Pedestrian Crossing Phase",
                type="manual_state",
                enabled=False,
            )
        ]
    )

    assert provider.is_active("pedestrian_phase_main") is False
