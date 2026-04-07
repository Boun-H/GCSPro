from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Any


@dataclass
class FactMetaData:
    name: str
    value_type: str = "float"
    default_value: float = 0.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    decimal_places: int = 3
    units: str = ""
    short_description: str = ""

    def clamp(self, value: float) -> float:
        result = float(value)
        if self.min_value is not None:
            result = max(float(self.min_value), result)
        if self.max_value is not None:
            result = min(float(self.max_value), result)
        return result


class Fact:
    def __init__(self, metadata: FactMetaData, value: Optional[float] = None):
        self.metadata = metadata
        initial = metadata.default_value if value is None else float(value)
        self._value = metadata.clamp(initial)

    @property
    def value(self) -> float:
        return float(self._value)

    def set_value(self, value: float):
        self._value = self.metadata.clamp(float(value))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.metadata.name,
            "value": float(self._value),
            "units": self.metadata.units,
            "description": self.metadata.short_description,
        }


class FactSystem:
    """QGC Fact/FatMetaData 的精简版：元数据驱动 + 值约束。"""

    def __init__(self):
        self._metadata: Dict[str, FactMetaData] = {}
        self._facts: Dict[str, Fact] = {}

    def register_metadata(self, metadata: FactMetaData):
        key = str(metadata.name).strip().upper()
        self._metadata[key] = metadata
        if key not in self._facts:
            self._facts[key] = Fact(metadata)

    def register_metadata_map(self, metadata_map: Dict[str, Dict[str, Any]]):
        for name, payload in (metadata_map or {}).items():
            if not isinstance(payload, dict):
                continue
            self.register_metadata(
                FactMetaData(
                    name=str(name),
                    value_type=str(payload.get("type", "float") or "float"),
                    default_value=float(payload.get("default", 0.0) or 0.0),
                    min_value=(None if payload.get("min") is None else float(payload.get("min"))),
                    max_value=(None if payload.get("max") is None else float(payload.get("max"))),
                    decimal_places=int(payload.get("decimals", 3) or 3),
                    units=str(payload.get("units", "") or ""),
                    short_description=str(payload.get("description", "") or ""),
                )
            )

    def update_values(self, values: Dict[str, float]):
        for name, value in (values or {}).items():
            self.set_value(name, value)

    def set_value(self, name: str, value: float):
        key = str(name).strip().upper()
        metadata = self._metadata.get(key)
        if metadata is None:
            metadata = FactMetaData(name=str(name), default_value=float(value))
            self.register_metadata(metadata)
        self._facts[key].set_value(float(value))

    def get_value(self, name: str, default: Optional[float] = None) -> Optional[float]:
        key = str(name).strip().upper()
        if key not in self._facts:
            return default
        return self._facts[key].value

    def get_fact(self, name: str) -> Optional[Fact]:
        return self._facts.get(str(name).strip().upper())

    def metadata_for(self, name: str) -> Optional[FactMetaData]:
        return self._metadata.get(str(name).strip().upper())

    def all_facts(self) -> Dict[str, Fact]:
        return dict(self._facts)

    def values_dict(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for key, fact in self._facts.items():
            result[fact.metadata.name] = float(fact.value)
        return result
