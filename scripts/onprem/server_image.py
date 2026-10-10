#!/usr/bin/env python3
"""Offline image replacement for an existing single-server k3d SQLite cluster.

No cluster deletion, anonymous-volume deletion, Terraform apply, or deployment.
Backups are age-encrypted streams. Config/Env/labels and node passwords never print.
"""
import argparse
import base64
import copy
import hashlib
import http.client
import io
import tarfile
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.parse import quote, urlencode

from onpremctl import run, write_json

FILES = ("/etc/rancher/node", "/bin/k3d-entrypoint.sh", "/bin/k3d-entrypoint-cgroupv2.sh",
         "/bin/k3d-entrypoint-dns.sh", "/bin/k3d-entrypoint-mounts.sh")


def checksum(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class Docker:
    def __init__(self):
        endpoint = json.loads(run(["docker", "context", "inspect"]).stdout)[0]["Endpoints"]["docker"]["Host"]
        endpoint = os.environ.get("DOCKER_HOST", endpoint)
        if not endpoint.startswith("unix://"):
            raise RuntimeError("only the local Docker Unix socket is supported")
        self.socket = endpoint[7:]

    def request(self, method, path, data=None, binary=False):
        connection = http.client.HTTPConnection("localhost", timeout=180)
        connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.sock.settimeout(180)
        connection.sock.connect(self.socket)
        body = data if binary else json.dumps(data).encode() if data is not None else None
        try:
            connection.request(method, path, body=body, headers={"Content-Type": "application/x-tar" if binary else "application/json"})
            response = connection.getresponse()
            raw = response.read()
            if response.status >= 300:
                # Docker's error body may repeat environment/config values.
                raise RuntimeError(f"Docker API {method} failed (HTTP {response.status})")
            return raw if binary else json.loads(raw) if raw else None
        finally:
            connection.close()

    def inspect(self, name):
        return self.request("GET", f"/containers/{quote(name, safe='')}/json")


def validate(info):
    name = info["Name"].lstrip("/")
    labels = info["Config"].get("Labels", {})
    if labels.get("k3d.role") != "server" or not name.endswith("-server-0"):
        raise RuntimeError("expected an existing k3d server-0")
    if len(info["NetworkSettings"]["Networks"]) != 1:
        raise RuntimeError("expected exactly one existing Docker network")
    if any(m["Type"] != "volume" for m in info["Mounts"]):
        raise RuntimeError("this procedure requires volume-backed mounts only")
    if "/var/lib/rancher/k3s" not in {m["Destination"] for m in info["Mounts"]}:
        raise RuntimeError("persistent k3s volume is missing")
    return name


def create_spec(info, image, *, volumes=None, network=None, isolated=False):
    """Preserve Config and runtime options; explicitly reattach every anonymous volume."""
    validate(info)
    config, host = copy.deepcopy(info["Config"]), copy.deepcopy(info["HostConfig"])
    config["Image"] = image
    host["Binds"] = [f"{(volumes or {}).get(m['Name'], m['Name'])}:{m['Destination']}:{'rw' if m['RW'] else 'ro'}"
                     for m in info["Mounts"]]
    host.pop("Mounts", None)
    original_network, endpoint = next(iter(info["NetworkSettings"]["Networks"].items()))
    selected = network or original_network
    # Preserve aliases but deliberately do not reserve IPAddress/EndpointID/MacAddress.
    networking = {"EndpointsConfig": {selected: {"Aliases": endpoint.get("Aliases") or []}}}
    if isolated:
        host["PortBindings"] = {}
        host["RestartPolicy"] = {"Name": "no", "MaximumRetryCount": 0}
        host["NetworkMode"] = selected
        config["Labels"] = {"one-tatchi.recovery-clone": "true"}
        # Never allow k3d to adopt or start this copy.
    return dict(config, HostConfig=host, NetworkingConfig=networking)


def encrypt_bytes(value, path, recipient):
    if path.exists():
        raise RuntimeError("backup destination already exists")
    result = subprocess.run(["age", "-r", recipient, "-o", str(path)], input=value, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError("backup encryption failed")
    path.chmod(0o600)


def decrypt_bytes(path, identity):
    result = subprocess.run(["age", "-d", "-i", str(identity), str(path)], capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError("backup decryption failed")
    return result.stdout


def volume_backup(volume, destination, recipient, helper):
    if destination.exists():
        raise RuntimeError("backup destination already exists")
    with tempfile.TemporaryFile() as errors:
        source = subprocess.Popen(["docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/tar",
                                   "--mount", f"type=volume,source={volume},target=/source,readonly",
                                   helper, "-czf", "-", "-C", "/source", "."], stdout=subprocess.PIPE, stderr=errors)
        encrypt = subprocess.Popen(["age", "-r", recipient, "-o", str(destination)], stdin=source.stdout, stderr=errors)
        source.stdout.close()
        try:
            encryption_code = encrypt.wait(timeout=1200)
            source_code = source.wait(timeout=30)
            if encryption_code or source_code:
                raise RuntimeError("volume backup failed")
        finally:
            for process in (source, encrypt):
                if process.poll() is None:
                    process.kill()
                    process.wait()
    destination.chmod(0o600)


def volume_restore(archive, identity, volume, helper):
    # Refuse nonempty volumes. Rollback uses new restored volumes, preserving damaged evidence.
    check = run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/sh", "--mount",
                 f"type=volume,source={volume},target=/target", helper, "-c", 'test -z "$(ls -A /target)"'], check=False)
    if check.returncode:
        raise RuntimeError("restore destination volume is not empty")
    with tempfile.TemporaryFile() as errors:
        decrypt = subprocess.Popen(["age", "-d", "-i", str(identity), str(archive)], stdout=subprocess.PIPE, stderr=errors)
        target = subprocess.Popen(["docker", "run", "--rm", "-i", "--network", "none", "--entrypoint", "/bin/tar", "--mount",
                                   f"type=volume,source={volume},target=/target", helper, "-xzf", "-", "-C", "/target"],
                                  stdin=decrypt.stdout, stdout=errors, stderr=errors)
        decrypt.stdout.close()
        try:
            target_code = target.wait(timeout=1200)
            source_code = decrypt.wait(timeout=30)
            if target_code or source_code:
                raise RuntimeError("volume restore or authenticated decryption failed")
        finally:
            for process in (decrypt, target):
                if process.poll() is None:
                    process.kill()
                    process.wait()


def backup(server, directory, recipient, identity, state=None, original_ip=None):
    api = Docker()
    info = api.inspect(server)
    validate(info)
    if info["State"]["Running"]:
        raise RuntimeError("stop the server gracefully before taking a consistent backup")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    if original_ip:
        ipaddress.IPv4Address(original_ip)
    metadata = {"container": info, "files": {}, "state": None, "original_ip": original_ip}
    for path in FILES:
        raw = api.request("GET", f"/containers/{server}/archive?" + urlencode({"path": path}), binary=True)
        metadata["files"][path] = base64.b64encode(raw).decode()
    if state:
        metadata["state"] = base64.b64encode(state.read_bytes()).decode()
    encrypted = directory / "metadata.age"
    plaintext = json.dumps(metadata).encode()
    encrypt_bytes(plaintext, encrypted, recipient)
    if decrypt_bytes(encrypted, identity) != plaintext:
        raise RuntimeError("metadata backup verification failed")
    for index, mount in enumerate(info["Mounts"]):
        volume_backup(mount["Name"], directory / f"volume-{index}.tar.gz.age", recipient, info["Image"])
    manifest = {"server": server, "image": info["Config"]["Image"], "volumes": len(info["Mounts"]),
                "files": {p.name: checksum(p) for p in directory.glob("*.age")}}
    write_json(directory / "manifest.json", manifest)
    return manifest


def read_backup(directory, identity):
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        path = directory / name
        if path.parent != directory or checksum(path) != digest:
            raise RuntimeError("backup checksum mismatch")
    return json.loads(decrypt_bytes(directory / "metadata.age", identity))


def inject(api, container, files):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as output:
        for path, encoded in files.items():
            if path not in FILES:
                raise RuntimeError("unexpected backup file")
            with tarfile.open(fileobj=io.BytesIO(base64.b64decode(encoded))) as source:
                for member in source:
                    if member.name.startswith("/") or ".." in Path(member.name).parts:
                        raise RuntimeError("invalid archive path")
                    member.name = str(Path(path).parent / member.name).lstrip("/")
                    output.addfile(member, source.extractfile(member) if member.isfile() else None)
    api.request("PUT", f"/containers/{container}/archive?path=/", archive.getvalue(), binary=True)


def replace(server, directory, identity, image):
    api = Docker()
    info = api.inspect(server)
    validate(info)
    if info["State"]["Running"]:
        raise RuntimeError("stop the server before replacement")
    saved = read_backup(directory, identity)
    if saved["container"]["Id"] != info["Id"]:
        raise RuntimeError("backup does not belong to the current container")
    cluster = info["Config"]["Labels"]["k3d.cluster"]
    servers = run(["docker", "ps", "-aq", "--filter", f"label=k3d.cluster={cluster}", "--filter", "label=k3d.role=server"]).stdout.split()
    if len(servers) != 1:
        raise RuntimeError("only a single-server cluster is supported")
    run(["docker", "image", "inspect", image])
    spec = create_spec(info, image)
    api.request("DELETE", f"/containers/{server}?v=false")
    try:
        api.request("POST", "/containers/create?" + urlencode({"name": server}), spec)
        inject(api, server, saved["files"])
    except Exception:
        # Before start no data has been upgraded. Restore the original container configuration.
        try:
            api.request("DELETE", f"/containers/{server}?v=false")
        except RuntimeError:
            pass
        api.request("POST", "/containers/create?" + urlencode({"name": server}), create_spec(info, info["Image"]))
        inject(api, server, saved["files"])
        raise RuntimeError("replacement failed; original stopped container was restored") from None
    current = api.inspect(server)
    if {m["Name"] for m in current["Mounts"]} != {m["Name"] for m in info["Mounts"]}:
        raise RuntimeError("volume identity changed; do not start the server")
    return {"server": server, "old_id": info["Id"], "new_id": current["Id"], "image": image, "volumes_preserved": True}


def restore_clone(directory, identity, name):
    """Restore the OLD image with its original IP on an unconnected dummy interface.

    --network=none prevents real tunnels/remote-write from contacting external systems.
    Keeping the original IP is essential for rehearsing rollback of the affected old k3s.
    The hostname, SQLite, node authentication and every data volume come from the backup.
    """
    if not name.startswith("t27-restore-"):
        raise RuntimeError("clone names must begin with t27-restore-")
    saved = read_backup(directory, identity)
    info = saved["container"]
    endpoint = next(iter(info["NetworkSettings"]["Networks"].values()))
    address = endpoint.get("IPAddress")
    # Docker clears a stopped container's IP. Backups also record it in metadata below.
    address = saved.get("original_ip") or address
    if not address:
        raise RuntimeError("backup requires the last running server IP for rollback rehearsal")
    ipaddress.IPv4Address(address)
    api = Docker()
    volumes = {}
    for index, mount in enumerate(info["Mounts"]):
        volume = f"{name}-{index}"
        api.request("POST", "/volumes/create", {"Name": volume, "Labels": {"one-tatchi.recovery-clone": name}})
        volume_restore(directory / f"volume-{index}.tar.gz.age", identity, volume, info["Image"])
        volumes[mount["Name"]] = volume
    spec = create_spec(info, info["Image"], volumes=volumes, isolated=True)
    spec.pop("NetworkingConfig", None)
    spec["HostConfig"]["NetworkMode"] = "none"
    spec["Entrypoint"] = ["/bin/sh", "-c",
        f"ip link add eth0 type dummy && ip addr add {address}/32 dev eth0 && ip link set eth0 up && "
        "ip route add default dev eth0 && exec /bin/k3d-entrypoint.sh \"$@\"", "--"]
    api.request("POST", "/containers/create?" + urlencode({"name": name}), spec)
    inject(api, name, saved["files"])
    api.request("POST", f"/containers/{name}/start")
    return {"clone": name, "network": "none", "original_ip": address, "volumes_restored": len(volumes),
            "image": info["Config"]["Image"]}


def rollback(server, directory, identity):
    """Restore data and image together, retaining the upgraded volumes for investigation."""
    saved = read_backup(directory, identity)
    original = saved["container"]
    api = Docker()
    current = api.inspect(server)
    validate(current)
    if current["State"]["Running"] or original["Name"].lstrip("/") != server:
        raise RuntimeError("rollback requires the matching server to be stopped")
    old_network = next(iter(original["NetworkSettings"]["Networks"]))
    if old_network not in current["NetworkSettings"]["Networks"]:
        raise RuntimeError("network identity changed")
    # Old k3s must regain its recorded Node IP. Fail before replacing anything if occupied.
    old_ip = saved.get("original_ip")
    network = api.request("GET", f"/networks/{quote(old_network, safe='')}")
    if not old_ip or any(c.get("IPv4Address", "").split("/")[0] == old_ip and cid != current["Id"]
                         for cid, c in network.get("Containers", {}).items()):
        raise RuntimeError("original node IP is unavailable; keep the isolated recovery copy")
    volumes = {}
    prefix = f"t27-rollback-{int(time.time())}"
    for index, mount in enumerate(original["Mounts"]):
        name = f"{prefix}-{index}"
        api.request("POST", "/volumes/create", {"Name": name, "Labels": {"one-tatchi.rollback": server}})
        volume_restore(directory / f"volume-{index}.tar.gz.age", identity, name, original["Image"])
        volumes[mount["Name"]] = name
    spec = create_spec(original, original["Image"], volumes=volumes)
    api.request("DELETE", f"/containers/{server}?v=false")
    api.request("POST", "/containers/create?" + urlencode({"name": server}), spec)
    inject(api, server, saved["files"])
    # Remains stopped. Start and confirm the dynamically assigned IP before accepting recovery.
    return {"server": server, "image": original["Config"]["Image"], "required_node_ip": old_ip,
            "volumes_restored": len(volumes), "upgraded_volumes_retained": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["backup", "replace", "restore-clone", "rollback"])
    parser.add_argument("--server", required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--recipient")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--image", default="rancher/k3s:v1.33.6-k3s1")
    parser.add_argument("--original-ip", help="last running IP, required for the isolated old-image rollback rehearsal")
    args = parser.parse_args()
    if args.command == "backup":
        if not args.recipient:
            parser.error("backup requires --recipient")
        result = backup(args.server, args.backup, args.recipient, args.identity, args.state, args.original_ip)
    elif args.command == "restore-clone":
        result = restore_clone(args.backup, args.identity, args.server)
    elif args.command == "rollback":
        result = rollback(args.server, args.backup, args.identity)
    else:
        result = replace(args.server, args.backup, args.identity, args.image)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print Docker payloads, configuration, subprocess stderr, or credentials.
        raise SystemExit(f"server image operation failed ({type(exc).__name__}); original volumes are retained")
