#!/usr/bin/env python3
"""k3d credentials stay in memory; only ExecCredential is emitted to its caller."""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def credentials(cluster):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", cluster):
        raise ValueError("invalid cluster name")
    raw = subprocess.run(["k3d", "kubeconfig", "get", cluster], capture_output=True, check=True, timeout=20)
    result = subprocess.run(
        ["kubectl", "config", "view", "--raw", "--kubeconfig=/dev/stdin", "-o", "json"],
        input=raw.stdout, capture_output=True, check=True, timeout=10,
    )
    config = json.loads(result.stdout)
    context = next(c["context"] for c in config["contexts"] if c["name"] == f"k3d-{cluster}")
    server = next(c["cluster"] for c in config["clusters"] if c["name"] == context["cluster"])
    user = next(u["user"] for u in config["users"] if u["name"] == context["user"])
    return {
        "endpoint": server["server"], "ca_certificate": server["certificate-authority-data"],
        "client_certificate": user["client-certificate-data"], "client_key": user["client-key-data"],
    }


def public_config(cluster, auth, helper=None):
    context = f"k3d-{cluster}"
    return {
        "apiVersion": "v1", "kind": "Config", "current-context": context,
        "clusters": [{"name": context, "cluster": {
            "server": auth["endpoint"], "certificate-authority-data": auth["ca_certificate"],
        }}],
        "contexts": [{"name": context, "context": {"cluster": context, "user": context}}],
        "users": [{"name": context, "user": {"exec": {
            "apiVersion": "client.authentication.k8s.io/v1", "interactiveMode": "Never",
            "command": sys.executable, "args": [str(helper or Path(__file__).resolve()), cluster],
            "env": [{"name": "PATH", "value": os.environ["PATH"]}],
        }}}],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cluster")
    p.add_argument("--config", type=Path, help="write a kubeconfig containing an exec reference, never a private key")
    a = p.parse_args()
    auth = credentials(a.cluster)
    if a.config:
        a.config.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(a.config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(public_config(a.cluster, auth), stream)
        return
    print(json.dumps({
        "apiVersion": "client.authentication.k8s.io/v1", "kind": "ExecCredential",
        "status": {
            "clientCertificateData": base64.b64decode(auth["client_certificate"]).decode(),
            "clientKeyData": base64.b64decode(auth["client_key"]).decode(),
        },
    }))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, StopIteration, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # subprocess output can include credential data; never echo it.
        print(f"k3d authentication failed ({type(exc).__name__})", file=sys.stderr)
        sys.exit(1)
