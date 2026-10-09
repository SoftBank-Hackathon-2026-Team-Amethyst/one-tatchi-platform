import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bundle
import publish


def image_archive(path, arches=("amd64", "arm64"), extra=None):
    files = {"oci-layout": b'{"imageLayoutVersion":"1.0.0"}'}
    def blob(content, media):
        data = json.dumps(content).encode()
        digest = bundle.digest(data)
        files["blobs/sha256/" + digest.split(":")[1]] = data
        return {"digest": digest, "size": len(data), "mediaType": media}
    manifests = []
    for arch in arches:
        config = blob({"os": "linux", "architecture": arch}, "application/vnd.oci.image.config.v1+json")
        image = blob({"schemaVersion": 2, "config": config, "layers": []}, "application/vnd.oci.image.manifest.v1+json")
        image["platform"] = {"os": "linux", "architecture": arch}
        manifests.append(image)
    index = blob({"schemaVersion": 2, "manifests": manifests}, "application/vnd.oci.image.index.v1+json")
    files["index.json"] = json.dumps({"schemaVersion": 2, "manifests": [index]}).encode()
    if extra:
        files.update(extra)
    with tarfile.open(path, "w") as tar:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))


class BundleTests(unittest.TestCase):
    def test_index_is_same_bytes_that_will_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.tar"
            image_archive(path)
            data = bundle.inspect_archive(path)
            self.assertEqual(set(data["platforms"]), {"linux/amd64", "linux/arm64"})
            with tarfile.open(path) as tar:
                root = json.load(tar.extractfile("index.json"))
                self.assertEqual(root["manifests"][0]["digest"], data["index_digest"])

    def test_missing_arch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.tar"
            image_archive(path, ("amd64",))
            with self.assertRaisesRegex(ValueError, "both"):
                bundle.inspect_archive(path)

    def test_scan_copy_exposes_both_leaf_digests_without_changing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.tar"
            image_archive(path)
            original = path.read_bytes()
            data = bundle.inspect_archive(path, Path(tmp) / "scan")
            index = json.loads((Path(tmp) / "scan/index.json").read_text())
            self.assertEqual({m["digest"] for m in index["manifests"]}, set(data["platforms"].values()))
            self.assertEqual(path.read_bytes(), original)

    def test_tar_traversal_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.tar"
            image_archive(path, extra={"../../escape": b"unsafe"})
            with self.assertRaisesRegex(ValueError, "unsafe"):
                bundle.inspect_archive(path)

    def test_bundle_cannot_be_reused_for_another_sha_or_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            image_archive(path / "image.tar")
            data = bundle.inspect_archive(path / "image.tar")
            data.update(context="be", repository="org/app", source_sha="good", run_id="12", producer_attempt=1,
                        scan_passed=sorted(bundle.PLATFORMS))
            for platform, config in data["configs"].items():
                arch = platform.split("/")[1]
                (path / f"{arch}-scan.json").write_text(json.dumps({"Metadata": {"ImageID": config,
                    "ImageConfig": {"os": "linux", "architecture": arch}}, "Results": []}))
            data["scan_reports"] = bundle.scan_evidence(path, data)
            (path / "verified.json").write_text(json.dumps(data))
            self.assertEqual(bundle.validate(path, "be", "org/app", "good", "12"), data)
            for sha, run in [("wrong", "12"), ("good", "13")]:
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    bundle.validate(path, "be", "org/app", sha, run)
            (path / "arm64-scan.json").write_text((path / "amd64-scan.json").read_text())
            with self.assertRaisesRegex(ValueError, "architecture mismatch"):
                bundle.validate(path, "be", "org/app", "good", "12")

    def test_incomplete_scan_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "verified.json").write_text(json.dumps({"context": "be", "repository": "o/r", "source_sha": "s", "run_id": "1", "producer_attempt": 1, "scan_passed": ["linux/amd64"]}))
            with self.assertRaisesRegex(ValueError, "scan evidence"):
                bundle.validate(path, "be", "o/r", "s", "1")


class PublishTests(unittest.TestCase):
    def test_same_digest_retry_does_not_copy_or_build(self):
        with patch.object(publish, "existing_digest", return_value="sha256:abc"), patch.object(publish, "command") as command:
            publish.publish(Path("bundle"), "registry/app", "sha", "sha256:abc", Path("auth"))
            command.assert_not_called()

    def test_different_existing_digest_is_never_overwritten(self):
        with patch.object(publish, "existing_digest", return_value="sha256:other"), patch.object(publish, "command") as command:
            with self.assertRaisesRegex(RuntimeError, "different digest"):
                publish.publish(Path("bundle"), "registry/app", "sha", "sha256:abc", Path("auth"))
            command.assert_not_called()

    def test_copy_preserves_all_architectures_without_build(self):
        with patch.object(publish, "existing_digest", side_effect=[None, "sha256:abc"]), patch.object(publish, "command") as command:
            publish.publish(Path("bundle"), "registry/app", "sha", "sha256:abc", Path("auth"))
            args = command.call_args.args[0]
            self.assertEqual(args[:4], ["skopeo", "copy", "--all", "--preserve-digests"])

    def test_permission_error_is_not_missing_image(self):
        denied = subprocess.CompletedProcess([], 1, b"", b"unauthorized")
        with patch.object(publish.subprocess, "run", return_value=denied), self.assertRaisesRegex(RuntimeError, "lookup failed"):
            publish.existing_digest("r/app", "sha", Path("auth"))

    def test_missing_manifest_is_recognized(self):
        missing = subprocess.CompletedProcess([], 1, b"", b"manifest unknown")
        with patch.object(publish.subprocess, "run", return_value=missing):
            self.assertIsNone(publish.existing_digest("r/app", "sha", Path("auth")))


if __name__ == "__main__":
    unittest.main()
