import base64
import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.analyze_tools import discover_log_files, preview_log_file, summarize_log_files
from core.firmware_tools import build_firmware_upgrade_plan, inspect_firmware_image


class AnalyzeAndFirmwareToolsTests(unittest.TestCase):
    def test_discover_log_files_and_summary(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first = root / "alpha.log"
            second = root / "beta.bin"
            ignored = root / "notes.txt"
            first.write_text("alpha telemetry\nline2", encoding="utf-8")
            second.write_bytes(b"\x01\x02\x03\x04")
            ignored.write_text("ignore me", encoding="utf-8")
            os.utime(first, (time.time() - 30, time.time() - 30))
            os.utime(second, None)

            discovered = discover_log_files(root, limit=10)
            self.assertEqual([item.path.name for item in discovered], ["beta.bin", "alpha.log"])

            summary = summarize_log_files(discovered)
            self.assertEqual(summary["total_files"], 2)
            self.assertIn(".bin", summary["by_extension"])
            self.assertIn(".log", summary["by_extension"])

    def test_preview_log_file_supports_text_and_binary(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            text_file = root / "flight.log"
            bin_file = root / "flight.bin"
            text_file.write_text("mode=AUTO\nbattery=91\n", encoding="utf-8")
            bin_file.write_bytes(b"\xAA\xBB\xCC\xDD")

            text_preview = preview_log_file(text_file)
            binary_preview = preview_log_file(bin_file)

            self.assertIn("mode=AUTO", text_preview)
            self.assertIn("文本预览", text_preview)
            self.assertIn("二进制预览", binary_preview)
            self.assertIn("AA BB CC DD", binary_preview)

    def test_inspect_firmware_image_for_bin_and_apj(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bin_file = root / "plane.bin"
            apj_file = root / "plane.apj"
            bin_file.write_bytes(b"firmware-image")
            apj_payload = {
                "board_id": 9,
                "description": "Test APJ",
                "image": base64.b64encode(b"payload-bytes").decode("ascii"),
            }
            apj_file.write_text(json.dumps(apj_payload), encoding="utf-8")

            bin_info = inspect_firmware_image(bin_file)
            apj_info = inspect_firmware_image(apj_file)

            self.assertEqual(bin_info.extension, ".bin")
            self.assertEqual(bin_info.size_bytes, len(b"firmware-image"))
            self.assertEqual(apj_info.extension, ".apj")
            self.assertEqual(apj_info.board_id, 9)
            self.assertEqual(apj_info.image_size, len(b"payload-bytes"))

    def test_build_firmware_upgrade_plan_prefers_serial_reconnect(self):
        info = inspect_firmware_image_bytes_for_test()
        plan = build_firmware_upgrade_plan(
            {
                "kind": "serial",
                "label": "COM7@115200",
                "payload": {"port": "COM7", "baud": 115200},
            },
            info,
        )

        self.assertTrue(plan["can_reconnect"])
        self.assertEqual(plan["port"], "COM7")
        self.assertEqual(plan["baud"], 115200)


def inspect_firmware_image_bytes_for_test():
    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "quick.bin"
        path.write_bytes(b"abc123")
        return inspect_firmware_image(path)


if __name__ == "__main__":
    unittest.main()
