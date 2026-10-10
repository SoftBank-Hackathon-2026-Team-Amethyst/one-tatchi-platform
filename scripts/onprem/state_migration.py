"""Explicit, encrypted-backup-first migration of the legacy local onprem state."""
import argparse
import base64
import copy
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

from onpremctl import check_ownership, cluster_exists, prepare_kubeconfig, run, state_path
from state_audit import contains_secret, artifact_files


def scrub(state):
    clean = copy.deepcopy(state)
    removed = []
    resources = []
    for resource in clean.get("resources", []):
        module = resource.get("module", "")
        address = f"{module}.{resource['type']}.{resource['name']}"
        database = bool(re.fullmatch(r'module\.database\["(?:test|prod)"\]', module))
        if (module == "module.cluster" and resource["type"] == "external" and resource["name"] == "kubeconfig"
                and resource.get("mode") == "data"):
            removed.append(address)
            continue
        if database and resource["type"] == "random_password" and resource["name"] == "this":
            removed.append(address)
            continue
        if database and resource["type"] == "kubernetes_secret_v1" and resource["name"] == "credentials":
            for instance in resource["instances"]:
                attributes = instance["attributes"]
                attributes["data"] = None
                attributes["binary_data"] = None
                attributes["data_wo_revision"] = 1
                instance["sensitive_attributes"] = []
            removed.append(address + ".data")
        resources.append(resource)
    clean["resources"] = resources
    for key in ("client_key", "client_certificate", "kubeconfig", "onprem_auth", "onprem_db_passwords"):
        if key in clean.get("outputs", {}):
            del clean["outputs"][key]
            removed.append(f"output.{key}")
    clean["serial"] = state["serial"] + 1
    return clean, removed


def secret_values(state):
    values = set()
    for resource in state.get("resources", []):
        for instance in resource.get("instances", []):
            attrs = instance.get("attributes", {})
            if resource["type"] == "random_password" and attrs.get("result"):
                values.add(attrs["result"])
            if resource["type"] == "kubernetes_secret_v1":
                for key, value in (attrs.get("data") or {}).items():
                    if key.lower() not in ("username",) and isinstance(value, str) and value:
                        values.add(value)
            if resource["type"] == "external":
                for key in ("client_key", "client_certificate"):
                    value = (attrs.get("result") or {}).get(key)
                    if value:
                        values.add(value)
    return values


def assert_clean(data, values):
    if contains_secret(data, values):
        raise RuntimeError("secret material remains; no files removed")


def archived_equivalent(data, archived):
    if data in archived:
        return True
    def normalize(raw):
        state = json.loads(raw)
        if not all(k in state for k in ("lineage", "serial", "resources")):
            raise ValueError("not a state")
        state["resources"].sort(key=lambda r: (r.get("module", ""), r["mode"], r["type"], r["name"]))
        for resource in state["resources"]:
            for instance in resource["instances"]:
                # Terraform's state writer materializes these empty/default metadata fields.
                instance.setdefault("sensitive_attributes", [])
                instance.setdefault("identity_schema_version", 0)
        return state
    try:
        current = normalize(data)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return False
    for original in archived:
        try:
            if current == normalize(original):
                return True
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            continue
    return False


def migrate(config, args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", required=True, help="age public recovery recipient")
    parser.add_argument("--identity", required=True, type=Path, help="recovery identity; used only to verify encrypted backup")
    parser.add_argument("--backup", required=True, type=Path, help="new .age backup outside Terraform root")
    parser.add_argument("--plan-file", action="append", default=[], type=Path, help="explicit old saved plan to archive/remove")
    a = parser.parse_args(args)
    root = Path(config["terraform_root"]).resolve()
    backup = a.backup.resolve()
    if backup.exists() or root == backup.parent or root in backup.parents or backup.suffix != ".age":
        raise RuntimeError("backup must be a new .age file outside the Terraform root")
    if any(os.environ.get(k) for k in ("TF_LOG", "TF_LOG_PROVIDER", "TF_LOG_CORE", "TF_LOG_PATH")):
        raise RuntimeError("Terraform debug logging must be disabled")
    # Fail before touching a state if a subsequent apply would restore the old secret-writing schema.
    modules = json.loads((root / ".terraform/modules/modules.json").read_text())["Modules"]
    database = next((m for m in modules if m["Key"] == "database"), None)
    cluster = next((m for m in modules if m["Key"] == "cluster"), None)
    if not database or not cluster:
        raise RuntimeError("init the updated onprem root before migration")
    db_source = (root / database["Dir"] / "main.tf").read_text()
    cluster_source = (root / cluster["Dir"] / "main.tf").read_text()
    variables = (root / "variables.tf").read_text()
    if "data_wo_revision" not in db_source or 'data "external"' in cluster_source or "ephemeral" not in variables:
        raise RuntimeError("updated ephemeral/write-only modules must be installed before migration")
    check_ownership(config, cluster_exists(config))
    prepare_kubeconfig(config)
    source = state_path(config)
    original = source.read_bytes()
    state = json.loads(original)
    if not state.get("lineage") or not isinstance(state.get("serial"), int):
        raise RuntimeError("missing state lineage/serial")
    # Never rewrite an unexplained state or silently migrate a different cluster's passwords.
    for resource in state.get("resources", []):
        if resource["type"] == "kubernetes_secret_v1" and resource["name"] == "credentials":
            for instance in resource["instances"]:
                attrs = instance["attributes"]
                namespace, name = attrs["id"].split("/", 1)
                live = json.loads(run(["kubectl", "get", "secret", name, "-n", namespace, "-o", "json"]).stdout)["data"]
                for key, value in (attrs.get("data") or {}).items():
                    if base64.b64decode(live[key]).decode() != value:
                        raise RuntimeError("state/live Secret differ; investigate before migration")
    clean, changed = scrub(state)
    values = secret_values(state)
    payload = (json.dumps(clean) + "\n").encode()
    assert_clean(payload, values)
    if (root / ".terraform.tfstate.lock.info").exists():
        raise RuntimeError("another Terraform operation holds the state lock")
    candidates = artifact_files(root, a.plan_file)
    files = {}
    for path in candidates:
        if path.is_symlink():
            raise RuntimeError("symlink state/backup/plan is not accepted")
        path = path.resolve()
        if path.parent != root or not path.is_file():
            raise RuntimeError("only regular files directly inside the configured Terraform root are accepted")
        files[path] = path.read_bytes()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo(path.name)
            info.size, info.mode = len(data), 0o600
            tar.addfile(info, io.BytesIO(data))
    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encrypted = subprocess.run(["age", "-r", a.recipient], input=archive.getvalue(), capture_output=True, check=True).stdout
    recovered = subprocess.run(["age", "-d", "-i", str(a.identity)], input=encrypted, capture_output=True, check=True).stdout
    if recovered != archive.getvalue():
        raise RuntimeError("backup recovery verification failed")
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encrypted)
        stream.flush()
        os.fsync(stream.fileno())
    if source.read_bytes() != original:
        raise RuntimeError("state changed during backup; retry after other Terraform operations finish")
    # Terraform performs serial/lineage checks and locking. No -force, remote resource operation, or state rm.
    subprocess.run(["terraform", f"-chdir={root}", "state", "push", "-"], input=payload, capture_output=True, check=True)
    current = json.loads(source.read_bytes())
    if current["lineage"] != state["lineage"] or current["serial"] < clean["serial"]:
        raise RuntimeError("unexpected state after migration; encrypted backup retained")
    def identities(document):
        return {(r.get("module", ""), r["type"], r["name"], str(i.get("index_key", "")), i.get("attributes", {}).get("id"))
                for r in document.get("resources", []) for i in r.get("instances", [])}
    if identities(current) != identities(clean):
        raise RuntimeError("resource identities changed; encrypted backup retained")
    assert_clean(source.read_bytes(), values)
    # state push can create a fresh .backup containing the old state. Remove only byte-identical archived material.
    for path in set(files) | set(root.glob("*.tfstate.backup*")):
        if path == source or not path.exists():
            continue
        data = path.read_bytes()
        if not archived_equivalent(data, files.values()):
            raise RuntimeError(f"unarchived/changed file retained: {path.name}")
        path.unlink()
    print(json.dumps({"changed_paths": changed, "backup": str(backup),
                      "backup_sha256": hashlib.sha256(encrypted).hexdigest(), "plaintext_files_removed": len(files) - 1}))
    return 0
