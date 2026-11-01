"""Offline fixture verification for GitHub-source restore; no network access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/restore_source_snapshot.py"
spec = importlib.util.spec_from_file_location("restore_source_snapshot", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class SnapshotRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dir = self.root / "source_transport"
        self.dir.mkdir()
        files = {}
        for p in mod.ROOT_FILES: files[p] = ("Content of " + p + "\n").encode()
        for i in range(36): files["src/midivolt/module%02d.py" % i] = ("def main(): return " + str(i) + "\n").encode()
        self.file_contents = files
        self.part_files = []
        chunks = []
        listing = []
        keys = sorted(files)
        for k in range(6):
            portion = keys[k * 7:(k+1)*7] if k < 5 else keys[35:]
            part = {"source_tree": "abc123", "files": []}
            for name in portion:
                content = files[name]
                sha = mod.git_blob_sha(content)
                part["files"].append({"path": name, "sha": sha, "content": content.decode()})
                listing.append({"path": name, "git_blob_sha": sha, "chunk": k})
            path = self.dir / ("part-%02d.json" % k)
            path.write_text(json.dumps(part, separators=(",", ":")), encoding="utf-8")
            self.part_files.append(path)
            chunks.append({"path": "source_transport/part-%02d.json" % k, "git_blob_sha": mod.git_blob_sha(path.read_bytes()), "files": len(portion)})
        self.manifest = {"format": "midivolt-offline-source-snapshot-v1", "source_commit": "abc123", "source_blob_count": 40, "package_module_count": 36, "chunks": chunks, "files": listing}
        self.save_manifest()

    def save_manifest(self):
        (self.dir / "MANIFEST.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_full_40_files_verified(self):
        manifest, files = mod.load_snapshot(self.root)
        self.assertEqual(len(files), 40)
        self.assertEqual(dict(files), self.file_contents)

    def test_restore_into_empty_destination(self):
        dest = self.root / "out"
        self.assertEqual(mod.main(["--root", str(self.root), "--destination", str(dest)]), 0)
        self.assertEqual((dest / "src/midivolt/module20.py").read_bytes(), self.file_contents["src/midivolt/module20.py"])

    def test_existing_destination_rejected(self):
        out = self.root / "used"
        out.mkdir()
        self.assertEqual(mod.main(["--root", str(self.root), "--destination", str(out)]), 2)

    def test_chunk_tamper_rejected(self):
        self.part_files[1].write_bytes(self.part_files[1].read_bytes() + b"\n")
        with self.assertRaisesRegex(mod.SnapshotError, "Git SHA mismatch in source chunk"):
            mod.load_snapshot(self.root)

    def test_manifest_sha_tamper_rejected(self):
        self.manifest["files"][2]["git_blob_sha"] = "0" * 40
        self.save_manifest()
        with self.assertRaisesRegex(mod.SnapshotError, "Source manifest SHA mismatch"):
            mod.load_snapshot(self.root)

    def test_path_traversal_rejected(self):
        self.assertFalse(mod.validate_relpath("../../pwn.py"))
        self.assertFalse(mod.validate_relpath("src/midivolt/../a.py"))
        self.assertFalse(mod.validate_relpath("src\\midivolt\\foo.py"))

    def test_missing_chunk_rejected(self):
        self.part_files[4].unlink()
        with self.assertRaisesRegex(mod.SnapshotError, "Missing/unsafe source chunk"):
            mod.load_snapshot(self.root)

    def test_verify_only_never_writes_files(self):
        self.assertEqual(mod.main(["--root", str(self.root), "--verify-only"]), 0)
        self.assertFalse((self.root / "out").exists())

if __name__ == "__main__": unittest.main()
