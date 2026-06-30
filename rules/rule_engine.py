from __future__ import annotations

from core.config_schema import (
    ConditionPredicateConfig,
    RuleConfig,
    ZoneEventPredicateConfig,
)
from rules.conditions import ConditionProvider
from rules.events import VehicleZoneEvent


class RuleEngine:
    def __init__(
        self,
        rules: list[RuleConfig],
        condition_provider: ConditionProvider,
    ):
        self.rules = [rule for rule in rules if rule.enabled]
        self.condition_provider = condition_provider

    @property
    def has_rules(self) -> bool:
        return bool(self.rules)

    def matching_rules(self, event: VehicleZoneEvent) -> list[RuleConfig]:
        return [rule for rule in self.rules if self._matches_rule(rule, event)]

    def _matches_rule(self, rule: RuleConfig, event: VehicleZoneEvent) -> bool:
        return all(
            self._matches_predicate(predicate, event) for predicate in rule.when.all
        )

    def _matches_predicate(
        self,
        predicate: ZoneEventPredicateConfig | ConditionPredicateConfig,
        event: VehicleZoneEvent,
    ) -> bool:
        if isinstance(predicate, ZoneEventPredicateConfig):
            return (
                predicate.event == event.event
                and predicate.zone_type == event.zone_type
            )

        if isinstance(predicate, ConditionPredicateConfig):
            return self.condition_provider.is_active(
                predicate.condition,
                event.timestamp_seconds,
            )

        return False
