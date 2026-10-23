import unittest

from validate_manifest import validate_manifest


def minimal_dataset(disposition="conditional_commercial_candidate"):
    return {
        "dataset_id": "test-set",
        "name": "Test dataset",
        "instrument_scope": ["guitar"],
        "data_kind": "audio_with_reference_midi",
        "official_url": "https://example.org/dataset",
        "declared_license": "CC-BY-4.0",
        "disposition": disposition,
        "intended_use": "benchmark",
        "rights_review": "pending",
    }


def cleared_dataset():
    dataset = minimal_dataset("commercially_cleared")
    dataset["commercial_clearance"] = {
        "status": "approved",
        "reviewer": "reviewer@example.org",
        "reviewed_at": "2026-10-23",
        "evidence_url": "https://example.org/license-evidence",
        "release_version": "1.0.0",
        "downloaded_at": "2026-10-23",
        "audio_license": "CC-BY-4.0",
        "annotation_license": "CC-BY-4.0",
        "attribution": "Dataset attribution text",
        "artifact_checksums": [
            {
                "path": "dataset/archive.zip",
                "sha256": "a" * 64,
            }
        ],
        "permissions": {
            "commercial_use": True,
            "benchmark": True,
        },
    }
    return dataset


class ManifestValidatorTests(unittest.TestCase):
    def test_inventory_accepts_well_formed_candidate(self):
        self.assertEqual(
            validate_manifest({"datasets": [minimal_dataset()]}, "inventory"),
            [],
        )

    def test_commercial_mode_blocks_unapproved_candidate(self):
        errors = validate_manifest({"datasets": [minimal_dataset()]}, "commercial")
        self.assertTrue(any("not 'commercially_cleared'" in error for error in errors))

    def test_commercial_mode_accepts_complete_clearance_record(self):
        self.assertEqual(
            validate_manifest({"datasets": [cleared_dataset()]}, "commercial"),
            [],
        )

    def test_commercial_mode_rejects_missing_permission(self):
        dataset = cleared_dataset()
        dataset["commercial_clearance"]["permissions"]["commercial_use"] = False
        errors = validate_manifest({"datasets": [dataset]}, "commercial")
        self.assertTrue(any("permissions.commercial_use must be true" in error for error in errors))

    def test_rejects_duplicate_dataset_ids(self):
        dataset_a = minimal_dataset()
        dataset_b = minimal_dataset()
        errors = validate_manifest({"datasets": [dataset_a, dataset_b]}, "inventory")
        self.assertTrue(any("duplicates" in error for error in errors))

    def test_rejects_invalid_checksum(self):
        dataset = cleared_dataset()
        dataset["commercial_clearance"]["artifact_checksums"][0]["sha256"] = "not-a-hash"
        errors = validate_manifest({"datasets": [dataset]}, "commercial")
        self.assertTrue(any("sha256 must be 64 hexadecimal characters" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
