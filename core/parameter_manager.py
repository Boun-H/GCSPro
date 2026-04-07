from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
import xml.etree.ElementTree as ET

from .fact_system import FactSystem


class ParameterManager:
    """精简版 ParameterManager：负责飞控参数与 FactSystem 同步。"""

    def __init__(self, fact_system: Optional[FactSystem] = None, metadata_xml_path: Optional[str] = None):
        self.fact_system = fact_system or FactSystem()
        self.metadata_source = ""
        if metadata_xml_path:
            self.load_metadata_from_xml(metadata_xml_path)

    def load_metadata_from_xml(self, xml_path: str) -> int:
        path = Path(str(xml_path or "")).expanduser()
        if not path.exists():
            return 0

        tree = ET.parse(path)
        root = tree.getroot()
        metadata_map: Dict[str, Dict] = {}
        for node in root.findall(".//parameter"):
            name = str(node.attrib.get("name", "") or "").strip()
            if not name:
                continue
            payload = {
                "type": str(node.attrib.get("type", "float") or "float").lower(),
                "default": node.attrib.get("default", 0.0),
                "min": None,
                "max": None,
                "decimals": 3,
                "units": "",
                "description": "",
            }
            min_node = node.find("min")
            max_node = node.find("max")
            unit_node = node.find("unit")
            decimal_node = node.find("decimal")
            short_desc_node = node.find("short_desc")
            if min_node is not None and min_node.text not in (None, ""):
                payload["min"] = float(min_node.text)
            if max_node is not None and max_node.text not in (None, ""):
                payload["max"] = float(max_node.text)
            if unit_node is not None and unit_node.text:
                payload["units"] = unit_node.text.strip()
            if decimal_node is not None and decimal_node.text:
                payload["decimals"] = int(float(decimal_node.text.strip()))
            if short_desc_node is not None and short_desc_node.text:
                payload["description"] = short_desc_node.text.strip()
            metadata_map[name] = payload

        self.fact_system.register_metadata_map(metadata_map)
        self.metadata_source = str(path)
        return len(metadata_map)

    def load_from_vehicle(self, mavlink_thread, timeout: float = 12.0) -> Dict[str, float]:
        params = mavlink_thread.request_all_parameters(timeout=timeout)
        self.fact_system.update_values(params)
        return dict(params)

    def apply_to_vehicle(self, mavlink_thread, values: Dict[str, float], timeout_per_param: float = 2.0) -> Dict[str, float]:
        sanitized = {}
        for name, value in (values or {}).items():
            self.fact_system.set_value(name, float(value))
            sanitized[str(name)] = float(self.fact_system.get_value(name, 0.0) or 0.0)
        applied = mavlink_thread.set_parameters(sanitized, timeout_per_param=timeout_per_param)
        self.fact_system.update_values(applied)
        return applied

    def export_to_file(self, file_path: str, payload: Optional[Dict] = None):
        from pathlib import Path as _Path
        import json

        target = _Path(file_path)
        data = payload if isinstance(payload, dict) and payload else self.fact_system.values_dict()
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_from_file(self, file_path: str) -> Dict[str, float]:
        from pathlib import Path as _Path
        import json

        source = _Path(file_path)
        data = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {}
        if isinstance(data, dict):
            nested = data.get("values")
            if isinstance(nested, dict):
                data = nested
            elif isinstance(data.get("params"), dict):
                data = data.get("params") or {}
        values: Dict[str, float] = {}
        for name, value in (data or {}).items():
            try:
                values[str(name)] = float(value)
            except (TypeError, ValueError):
                continue
        self.fact_system.update_values(values)
        return values
