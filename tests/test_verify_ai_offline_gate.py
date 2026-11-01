"""Dependency-free validator regression; no provider, model or network."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_ai_offline.py"
spec = importlib.util.spec_from_file_location("verify_ai_offline", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class JunitGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.xml = Path(self.temp.name) / "test.junit.xml"

    def write(self, tests=40, failures=0, errors=0, skipped=0, cases=None):
        import xml.etree.ElementTree as ET
        suites = ET.Element("testsuites")
        suite = ET.SubElement(suites, "testsuite", tests=str(tests),
                              failures=str(failures), errors=str(errors),
                              skipped=str(skipped))
        for i in range(tests if cases is None else cases):
            ET.SubElement(suite, "testcase", name="case" + str(i))
        ET.ElementTree(suites).write(self.xml, encoding="utf-8", xml_declaration=True)
        return gate.inspect_junit(self.xml)

    def test_valid_40_cases(self):
        self.assertEqual(self.write()["tests"], 40)

    def test_skipped_case_is_detected(self):
        self.assertEqual(self.write(skipped=1)["skipped"], 1)

    def test_missing_case_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Testcase count differs"):
            self.write(cases=39)

    def test_malformed_report_is_rejected(self):
        self.xml.write_text("<notxml", encoding="utf-8")
        import xml.etree.ElementTree as ET
        with self.assertRaises(ET.ParseError):
            gate.inspect_junit(self.xml)

    def test_negative_counts_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            self.write(skipped=-1)

    def test_zero_tests_is_detected(self):
        self.assertEqual(self.write(tests=0)["tests"], 0)


if __name__ == "__main__":
    unittest.main()
