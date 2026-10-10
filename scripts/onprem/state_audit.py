"""Read-only checks of local Terraform artifacts against live credentials.

Values and archive contents stay in memory. Reports contain file names/counts only.
This checks the declared files, not every copy or historical disk block on a host.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import quote, quote_plus


def secret_needles(values):
    needles = set()
    for value in values:
        if not value:
            continue
        raw = value.encode()
        needles.update((raw, base64.b64encode(raw), base64.urlsafe_b64encode(raw),
                        quote(value, safe="").encode(), quote_plus(value, safe="").encode()))
        for ascii_only in (True, False):
            needles.add(json.dumps(value, ensure_ascii=ascii_only)[1:-1].encode())
    return needles


def contains_secret(data, values):
    needles = secret_needles(values)
    private_key = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")

    def matches(raw):
        return any(needle in raw for needle in needles) or bool(private_key.search(raw))

    def stored_credentials(resource):
        kind = resource.get("type")
        if kind not in ("kubernetes_secret_v1", "random_password", "external"):
            return False
        attributes = [instance.get("attributes", {}) for instance in resource.get("instances", []) or []]
        attributes += [resource.get("values", {})]
        change = resource.get("change") or {}
        attributes += [change.get("before"), change.get("after")]
        for attrs in attributes:
            if not isinstance(attrs, dict):
                continue
            if kind == "kubernetes_secret_v1" and (attrs.get("data") or attrs.get("binary_data")):
                return True
            if kind == "random_password" and attrs.get("result"):
                return True
            if kind == "external" and any((attrs.get("result") or {}).get(key)
                                          for key in ("client_key", "client_certificate", "kubeconfig")):
                return True
        return False

    def inspect(raw, depth=0):
        if matches(raw):
            return True
        stream = io.BytesIO(raw)
        if zipfile.is_zipfile(stream):
            if depth >= 3:
                raise RuntimeError("archive nesting limit exceeded; audit incomplete")
            with zipfile.ZipFile(stream) as archive:
                if sum(item.file_size for item in archive.infolist()) > 128 * 1024 * 1024:
                    raise RuntimeError("archive size limit exceeded; audit incomplete")
                return any(inspect(archive.read(item), depth + 1) for item in archive.infolist() if not item.is_dir())
        # JSON may contain escaped strings, nested JSON or base64 Secret/PG_URL values.
        try:
            document = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return False
        pending = [document]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                # Also reject recognized legacy storage fields after credentials rotate.
                if stored_credentials(item):
                    return True
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, str):
                encoded = item.encode()
                if matches(encoded):
                    return True
                try:
                    decoded = base64.b64decode(encoded, validate=True)
                except ValueError:
                    continue
                if matches(decoded):
                    return True
        return False

    return inspect(data)


def artifact_files(root, extra=()):
    """Include old state backups, binary plans (even without a suffix), and show JSON."""
    root = Path(root).resolve()
    candidates = {root / "terraform.tfstate", *root.glob("*.tfstate.backup*"),
                  *root.glob("*.tfplan"), *(Path(path) for path in extra)}
    for path in root.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                if "tfplan" in archive.namelist():
                    candidates.add(path)
        elif path.suffix == ".json":
            try:
                data = json.loads(path.read_bytes())
                if isinstance(data, dict) and "terraform_version" in data and any(
                        key in data for key in ("planned_values", "values", "resources")):
                    candidates.add(path)
            except (ValueError, UnicodeDecodeError):
                pass
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("audit requires regular, existing files; symlinks are not accepted")
    return sorted(candidates)


def live_values(config):
    # Import lazily so state_migration can use the pure scanner without a cycle.
    from onpremctl import check_ownership, cluster_exists, run
    from kube_auth import credentials
    check_ownership(config, cluster_exists(config))
    auth = credentials(config["cluster"])
    kubeconfig = Path(config["home"]) / "kubeconfig.json"
    if not kubeconfig.is_file():
        raise RuntimeError("managed exec kubeconfig is required; audit incomplete")
    values = {auth[key] for key in ("client_key", "client_certificate")}
    values.update(base64.b64decode(value).decode() for value in tuple(values))
    required = [(config["secret_namespace"], f"{config['service']}-db-{env}-credentials")
                for env in config["environments"]]
    optional = [("monitoring", "deploy-metrics-remote-write"), ("tailscale", "operator-oauth")]
    checked = []
    for namespace, name in required + optional:
        raw = run(["kubectl", "--kubeconfig", kubeconfig, "get", "secret", name, "-n", namespace,
                   "--ignore-not-found", "-o", "json"]).stdout
        if not raw.strip():
            if (namespace, name) in required:
                raise RuntimeError("required DB credentials are absent; audit incomplete")
            continue
        data = json.loads(raw).get("data", {})
        keys = set(data) - {"username", "client_id"}
        required_key = "client_secret" if namespace == "tailscale" else "password"
        if required_key not in keys or any(not data[key] for key in keys):
            raise RuntimeError("empty credential Secret; audit incomplete")
        values.update(base64.b64decode(data[key]).decode() for key in keys)
        checked.append(f"{namespace}/{name}")
    return values, checked


def audit(config, args):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", action="append", default=[], type=Path,
                        help="additional plaintext artifact/copy, including outside the Terraform root")
    a = parser.parse_args(args)
    values, checked = live_values(config)
    home = Path(config["home"])
    root = Path(config["terraform_root"])
    extra = [*a.file, *root.glob("*.tfvars"), *root.glob("*.tfvars.json"),
             *(p for p in (home / "config.json", home / "kubeconfig.json") if p.exists())]
    files = artifact_files(config["terraform_root"], extra)
    results = []
    for path in files:
        data = path.read_bytes()
        found = contains_secret(data, values)
        if path.read_bytes() != data:
            raise RuntimeError("artifact changed during audit; repeat after Terraform finishes")
        results.append({"file": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                        "secret_found": found})
    if any(hashlib.sha256(Path(item["file"]).read_bytes()).hexdigest() != item["sha256"] for item in results):
        raise RuntimeError("artifact changed during audit; repeat after Terraform finishes")
    passed = not any(item["secret_found"] for item in results)
    print(json.dumps({"passed": passed, "profile": config["profile"], "files": results,
                      "credential_sources": checked, "private_values_logged": False}))
    return int(not passed)
