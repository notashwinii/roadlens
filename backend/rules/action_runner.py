from __future__ import annotations

from dataclasses import dataclass

from core.config_schema import RuleConfig
from rules.events import VehicleZoneEvent


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    rule_name: str
    event: VehicleZoneEvent
    actions: list[str]

    def to_result_metadata(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "zone_id": self.event.zone_id,
            "zone_type": self.event.zone_type,
            "zone_name": self.event.zone_name,
            "event": self.event.event,
            "actions": list(self.actions),
        }


class ActionRunner:
    def build_match(self, rule: RuleConfig, event: VehicleZoneEvent) -> RuleMatch:
        return RuleMatch(
            rule_id=rule.id,
            rule_name=rule.name,
            event=event,
            actions=list(rule.actions),
        )
