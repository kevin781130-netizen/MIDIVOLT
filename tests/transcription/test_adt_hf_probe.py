"""Metadata-only test for ADT_STR Hub revision/provenance preflight."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from midivolt.adt_hf_probe import VARIANT, probe_model


class ProbeTests(unittest.TestCase):
    SHA = "a" * 40

    def test_requires_pinned_full_revision(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            probe_model("main", client=Mock())

    def test_reports_missing_files_instead_of_guessing(self):
        fake = SimpleNamespace(
            sha=self.SHA,
            siblings=[SimpleNamespace(
                rfilename=f"{VARIANT}/model.safetensors",
                size=2048, blob_id="abc", lfs={"sha256": "f" * 64},
            )],
            card_data=SimpleNamespace(license="cc-by-sa-4.0"),
        )
        provider = Mock()
        provider.model_info.return_value = fake
        info = probe_model(self.SHA, client=provider)
        self.assertIn(f"{VARIANT}/adt_config.yaml", info["missing_files"])
        self.assertEqual(info["license_gate"], "research_only_not_commercially_cleared")
        provider.model_info.assert_called_once_with(
            "Pierfrancesco/adt-str", revision=self.SHA, files_metadata=True,
        )

    def test_rejects_unexpected_remote_revision(self):
        provider = Mock()
        provider.model_info.return_value = SimpleNamespace(
            sha="b" * 40, siblings=[], card_data=None,
        )
        with self.assertRaisesRegex(RuntimeError, "Revision mismatch"):
            probe_model(self.SHA, client=provider)

    def test_compatible_file_names_pass_metadata_preflight(self):
        provider = Mock()
        provider.model_info.return_value = SimpleNamespace(
            sha=self.SHA,
            siblings=[
                SimpleNamespace(rfilename=f"{VARIANT}/adt_config.yaml",
                                size=1234, blob_id="abc", lfs=None),
                SimpleNamespace(rfilename=f"{VARIANT}/model.safetensors",
                                size=10000, blob_id="def", lfs=None),
            ],
            card_data=None,
        )
        info = probe_model(self.SHA, client=provider)
        self.assertEqual(info["missing_files"], [])
        self.assertEqual(len(info["files"]), 2)
        self.assertIsNone(info["declared_license"])


if __name__ == "__main__":
    unittest.main()
