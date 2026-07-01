from __future__ import annotations

from core.config_schema import ConditionConfig


class ConditionProvider:
    def __init__(self, conditions: list[ConditionConfig]):
        self._conditions = {
            condition.id: condition for condition in conditions if condition.enabled
        }

    def is_active(
        self,
        condition_id: str,
        timestamp_seconds: float | None = None,
    ) -> bool:
        condition = self._conditions.get(condition_id)
        if condition is None:
            return False

        if condition.type == "always_true":
            return True

        return condition.type == "manual_state"
