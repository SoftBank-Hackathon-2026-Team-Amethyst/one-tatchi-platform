#!/usr/bin/env python3
"""Publish checked OCI bytes to a target registry without building or changing existing tags."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from bundle import digest, key, validate


def command(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed (exit {result.returncode})")
    return result.stdout


def existing_digest(repository, tag, authfile):
    result = subprocess.run(["skopeo", "inspect", "--authfile", str(authfile), "--raw", f"docker://{repository}:{tag}"], capture_output=True)
    if result.returncode == 0:
        return digest(result.stdout)
    if re.search(rb"manifest unknown|MANIFEST_UNKNOWN|manifest.*not found|manifest.*404", result.stderr):
        return None
    # Permission, transport, TLS and missing repository errors never mean "safe to overwrite".
    raise RuntimeError("registry lookup failed; refusing to treat it as a missing tag")


def publish(bundle_dir, repository, tag, expected, authfile):
    found = existing_digest(repository, tag, authfile)
    if found and found != expected:
        raise RuntimeError(f"existing tag has different digest: {repository}:{tag}")
    if not found:
        command(["skopeo", "copy", "--all", "--preserve-digests", "--authfile", str(authfile),
                 f"oci-archive:{bundle_dir / 'image.tar'}", f"docker://{repository}:{tag}"])
    if existing_digest(repository, tag, authfile) != expected:
        raise RuntimeError("published index digest mismatch")


def main():
    target = os.environ["TARGET"]
    sha = os.environ["GITHUB_SHA"]
    authfile = Path(os.environ["RUNNER_TEMP"]) / "t27-registry-auth.json"
    if target == "aws":
        registry = os.environ["ECR_REGISTRY"]
        username = "AWS"
        password = command(["aws", "ecr", "get-login-password"])
    elif target == "gcp":
        registry = f"{os.environ['GCP_REGION']}-docker.pkg.dev"
        username = "oauth2accesstoken"
        password = command(["gcloud", "auth", "print-access-token"])
    elif target == "onprem":
        registry = "ghcr.io"
        username = os.environ["GITHUB_ACTOR"]
        password = os.environ["GH_TOKEN"]
    else:
        raise ValueError("invalid target")
    try:
        command(["skopeo", "login", "--authfile", str(authfile), "--username", username, "--password-stdin", registry], input=password)
        authfile.chmod(0o600)
        images = {}
        services = json.loads(os.environ["SERVICES"])
        if not isinstance(services, list) or not services:
            raise ValueError("services must be a nonempty array")
        for service in services:
            name, context = service["name"], service["path"]
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in images:
                raise ValueError("invalid/duplicate service name")
            directory = Path(os.environ["BUNDLES"]) / f"checked-image-{os.environ['GITHUB_RUN_ID']}-{key(context)}"
            data = validate(directory, context, os.environ["GITHUB_REPOSITORY"], sha, os.environ["GITHUB_RUN_ID"])
            if target == "gcp":
                repository = f"{registry}/{os.environ['GCP_PROJECT']}/{name}/{name}"
            elif target == "onprem":
                repository = f"{registry}/{os.environ['GITHUB_REPOSITORY_OWNER'].lower()}/{name}"
            else:
                repository = f"{registry}/{name}"
            publish(directory, repository, sha, data["index_digest"], authfile)
            images[name] = {"repository": repository, "digest": data["index_digest"], "source_sha": sha}
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write("images=" + json.dumps(images, separators=(",", ":")) + "\n")
    finally:
        authfile.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, FileNotFoundError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
