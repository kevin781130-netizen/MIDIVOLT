# Commercial Dataset Gate

The manifest validator is fail-closed by default. It validates recorded metadata; it does not determine legal rights independently.

## Run the inventory check

From the repository root:

    python tests/benchmark/validate_manifest.py --mode inventory

This checks required dataset fields, valid dispositions, source URLs, and duplicate IDs. A PASS means only that the registry is structurally usable.

## Run the commercial gate

    python tests/benchmark/validate_manifest.py --mode commercial

The commercial gate exits with code 1 until every dataset in the manifest has disposition commercially_cleared and an evidence-backed commercial_clearance record. This is intentional: conditional candidates, research-only datasets, and unresolved licenses must not silently pass.

Each clearance record must contain:

- status set to approved, reviewer, review date, and a URL to the permission/license evidence;
- exact release version and download date;
- separate audio and annotation/MIDI license fields;
- attribution text;
- at least one artifact path and SHA-256 checksum;
- explicit permissions.commercial_use set to true and permissions.benchmark set to true.

A checksum establishes file identity, not permission. The reviewer must check the actual license and underlying rights. If training, redistribution, or hosted processing is intended, document those permissions separately before use.

## Run the tests

    python -m unittest discover -s tests/benchmark -p "test_*.py"

Tests use only Python's standard library and synthetic metadata fixtures. They do not download or redistribute any dataset.
