#!/usr/bin/env python3
"""Validate checked OCI bundles without trusting their manifest or archive paths."""
import argparse
import hashlib
import json
import os
import re
import tarfile
from pathlib import Path

PLATFORMS = {"linux/amd64", "linux/arm64"}


def key(context):
    return hashlib.sha256(context.encode()).hexdigest()[:16]


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def inspect_archive(path, extract=None):
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        names = [m.name.removeprefix("./") for m in members]
        if len(names) != len(set(names)):
            raise ValueError("duplicate OCI archive path")
        lookup = dict(zip(names, members))
        for name, member in lookup.items():
            if member.isdir():
                continue
            if not member.isfile() or not re.fullmatch(r"(?:index.json|oci-layout|blobs/sha256/[0-9a-f]{64})", name):
                raise ValueError("unsafe OCI archive member")
        def read(name):
            return archive.extractfile(lookup[name]).read()
        def blob(descriptor):
            algorithm, value = descriptor["digest"].split(":", 1)
            if algorithm != "sha256":
                raise ValueError("unsupported OCI digest")
            data = read(f"blobs/sha256/{value}")
            if digest(data) != descriptor["digest"] or len(data) != descriptor["size"]:
                raise ValueError("OCI blob digest/size mismatch")
            return data
        index = read("index.json")
        content = json.loads(index)
        # buildx exports an OCI layout index pointing at the actual multi-platform image index.
        if len(content["manifests"]) == 1 and "index" in content["manifests"][0].get("mediaType", ""):
            index = blob(content["manifests"][0])
            content = json.loads(index)
        platforms, configs = {}, {}
        for item in content["manifests"]:
            platform = item.get("platform", {})
            name = f"{platform.get('os')}/{platform.get('architecture')}"
            if name not in PLATFORMS or name in platforms:
                raise ValueError("unexpected/missing/duplicate image architecture")
            manifest = json.loads(blob(item))
            config = json.loads(blob(manifest["config"]))
            if f"{config.get('os')}/{config.get('architecture')}" != name:
                raise ValueError("platform differs from image config")
            for layer in manifest.get("layers") or []:
                blob(layer)
            platforms[name] = item["digest"]
            configs[name] = manifest["config"]["digest"]
        if set(platforms) != PLATFORMS:
            raise ValueError("both amd64 and arm64 are required")
        if extract:
            for name, member in lookup.items():
                if member.isfile():
                    dest = Path(extract) / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(read(name))
            # Trivy selects a digest only among top-level descriptors. Flatten the *scan copy*
            # of a Buildx wrapper so arm64 never accidentally scans its first (amd64) child.
            # image.tar and the actual image index bytes/digest remain unchanged.
            (Path(extract) / "index.json").write_bytes(index)
        return {"index_digest": digest(index), "platforms": platforms, "configs": configs,
                "archive_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def scan_evidence(directory, layout):
    hashes = {}
    for platform in sorted(PLATFORMS):
        raw = (Path(directory) / f"{platform.split('/')[1]}-scan.json").read_bytes()
        report = json.loads(raw)
        metadata = report["Metadata"]
        config = metadata["ImageConfig"]
        if f"{config['os']}/{config['architecture']}" != platform or metadata["ImageID"] != layout["configs"][platform]:
            raise ValueError("scan report image/architecture mismatch")
        for result in report.get("Results", []):
            if any(v.get("Severity") in ("HIGH", "CRITICAL") and v.get("FixedVersion") for v in result.get("Vulnerabilities") or []):
                raise ValueError("blocking vulnerabilities remain in scan report")
        hashes[platform] = hashlib.sha256(raw).hexdigest()
    return hashes


def validate(directory, context, repository, sha, run_id):
    directory = Path(directory)
    data = json.loads((directory / "verified.json").read_text())
    for field, value in {"context": context, "repository": repository, "source_sha": sha, "run_id": str(run_id)}.items():
        if data.get(field) != value:
            raise ValueError(f"bundle {field} mismatch")
    if data.get("scan_passed") != sorted(PLATFORMS) or type(data.get("producer_attempt")) is not int or data["producer_attempt"] < 1:
        raise ValueError("bundle has no complete scan evidence")
    actual = inspect_archive(directory / "image.tar")
    if any(data.get(field) != value for field, value in actual.items()):
        raise ValueError("bundle content differs from checked metadata")
    if data.get("scan_reports") != scan_evidence(directory, actual):
        raise ValueError("scan report digest mismatch")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["key", "inspect", "record", "validate"])
    parser.add_argument("value")
    parser.add_argument("--extract")
    args = parser.parse_args()
    if args.command == "key":
        print(key(args.value))
    elif args.command == "inspect":
        print(json.dumps(inspect_archive(args.value, args.extract)))
    elif args.command == "record":
        directory = Path(args.value)
        data = inspect_archive(directory / "image.tar")
        data["scan_reports"] = scan_evidence(directory, data)
        data.update(context=os.environ["CONTEXT"], repository=os.environ["GITHUB_REPOSITORY"],
                    source_sha=os.environ["GITHUB_SHA"], run_id=os.environ["GITHUB_RUN_ID"],
                    producer_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]), scan_passed=sorted(PLATFORMS))
        (directory / "verified.json").write_text(json.dumps(data, indent=2) + "\n")
    else:
        print(json.dumps(validate(args.value, os.environ["CONTEXT"], os.environ["GITHUB_REPOSITORY"],
                                  os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"])))


if __name__ == "__main__":
    main()
