import unittest
from pathlib import Path

from core.fact_system import FactMetaData, FactSystem
from core.parameter_manager import ParameterManager


class FactSystemTests(unittest.TestCase):
    def test_metadata_clamp(self):
        metadata = FactMetaData(name="WPNAV_SPEED", min_value=100.0, max_value=2000.0, default_value=500.0)
        self.assertEqual(metadata.clamp(10.0), 100.0)
        self.assertEqual(metadata.clamp(3000.0), 2000.0)

    def test_fact_system_register_and_update(self):
        fs = FactSystem()
        fs.register_metadata(
            FactMetaData(name="WPNAV_SPEED", min_value=100.0, max_value=2000.0, default_value=500.0)
        )
        fs.set_value("WPNAV_SPEED", 3000.0)
        self.assertEqual(fs.get_value("WPNAV_SPEED"), 2000.0)

    def test_register_metadata_map(self):
        fs = FactSystem()
        fs.register_metadata_map(
            {
                "PSC_ACCZ_P": {"default": 0.2, "min": 0.0, "max": 1.0, "units": "-", "description": "Z轴P"},
            }
        )
        fs.update_values({"PSC_ACCZ_P": 1.5})
        self.assertAlmostEqual(fs.get_value("PSC_ACCZ_P"), 1.0, places=6)

    def test_parameter_manager_loads_xml_metadata(self):
        metadata_path = Path(__file__).resolve().parent.parent / "references" / "ardupilot" / "ParameterFactMetaData.xml"
        manager = ParameterManager(metadata_xml_path=str(metadata_path))
        self.assertGreater(manager.load_metadata_from_xml(str(metadata_path)), 0)
        metadata = manager.fact_system.metadata_for("ctl_bw")
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.units, "Hertz")


if __name__ == "__main__":
    unittest.main()
