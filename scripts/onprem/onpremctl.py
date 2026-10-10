#!/usr/bin/env python3
"""Local macOS onprem lifecycle. Startup never applies Terraform or deploys apps."""
import argparse
import base64
import fcntl
import json
import os
import plistlib
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from kube_auth import credentials, public_config
from tunnel import resolve
from deadline import budget, remaining, pause

BASE = Path.home() / "Library/Application Support/one-tatchi/onprem"


def run(args, *, check=True, **kwargs):
    kwargs.setdefault("timeout", 30)
    kwargs["timeout"] = remaining(kwargs["timeout"])
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True, text=True, **kwargs)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{Path(str(args[0])).name} timed out") from None
    if check and result.returncode:
        # Terraform/kubernetes errors may contain values. Only the command name/status is safe here.
        raise RuntimeError(f"{Path(str(args[0])).name} failed (exit {result.returncode})")
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def load_config(path):
    config = json.loads(path.read_text())
    for key in ("profile", "cluster", "service"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", config.get(key, "")):
            raise ValueError(f"invalid {key}")
    for key in ("terraform_root", "runner_dir"):
        if not Path(config[key]).is_absolute():
            raise ValueError(f"{key} must be absolute")
    config.setdefault("environments", ["test", "prod"])
    if not config["environments"] or any(e not in ("test", "prod") for e in config["environments"]):
        raise ValueError("environments must contain test/prod")
    config.setdefault("secret_namespace", "platform")
    config.setdefault("api_port", 6550)
    version = config.get("kubernetes_version")
    if version is not None and not re.fullmatch(r"v\d+\.\d+\.\d+-k3s\d+", version):
        raise ValueError("kubernetes_version must be a Docker tag such as v1.33.6-k3s1")
    if not isinstance(config["api_port"], int) or not 1024 <= config["api_port"] <= 65535:
        raise ValueError("invalid api_port")
    config["home"] = str(BASE / config["profile"])
    return config


def state_path(config):
    return Path(config["terraform_root"]) / "terraform.tfstate"


def cluster_exists(config):
    # A failed Docker/API command is not evidence that the cluster is absent.
    clusters = json.loads(run(["k3d", "cluster", "list", "-o", "json"]).stdout)
    return any(c["name"] == config["cluster"] for c in clusters)


def check_ownership(config, exists):
    path = state_path(config)
    if exists and not path.exists():
        raise RuntimeError("cluster exists but its local Terraform state is missing; refusing adoption/recreation")
    if path.exists():
        state = json.loads(path.read_text())
        names = [i.get("attributes", {}).get("input", {}).get("value", {}).get("name")
                 for r in state.get("resources", []) if r.get("module") == "module.cluster" and r["type"] == "terraform_data"
                 for i in r.get("instances", [])]
        if config["cluster"] not in names:
            raise RuntimeError("state does not own the configured cluster")
        if not exists:
            raise RuntimeError("state exists but cluster is absent; restore the existing cluster, do not recreate its DB")


def prepare_kubeconfig(config):
    auth = credentials(config["cluster"])
    path = Path(config["home"]) / "kubeconfig.json"
    write_json(path, public_config(config["cluster"], auth))
    os.environ["KUBECONFIG"] = str(path)
    return auth


def labels(config):
    prefix = f"dev.onetatchi.onprem.{config['profile']}"
    return {name: f"{prefix}.{name}" for name in ("awake", "restore", "runner", "urls")}


def plists(config, interpreter=sys.executable):
    home = Path(config["home"])
    cli = home / "bin/onpremctl.py"
    config_path = home / "config.json"
    common = {
        "RunAtLoad": True, "ThrottleInterval": 30,
        "EnvironmentVariables": {"PATH": config["path"], "ONPREM_CLUSTER": config["cluster"], "ONPREM_PROFILE": config["profile"]},
    }
    result = {}
    for name, label in labels(config).items():
        result[name] = dict(common, Label=label,
                            StandardOutPath=str(home / f"logs/{name}.log"),
                            StandardErrorPath=str(home / f"logs/{name}.error.log"))
    result["awake"].update(ProgramArguments=["/usr/bin/caffeinate", "-s"], KeepAlive=True)
    result["restore"].update(ProgramArguments=[interpreter, str(cli), "--config", str(config_path), "restore"],
                             KeepAlive={"SuccessfulExit": False})
    result["runner"].update(ProgramArguments=[interpreter, str(cli), "--config", str(config_path), "runner"], KeepAlive=True)
    result["urls"].update(ProgramArguments=[interpreter, str(cli), "--config", str(config_path), "refresh-urls"], StartInterval=30)
    return result


def install(config, start=True):
    if sys.platform != "darwin":
        raise RuntimeError("launchd install is supported on macOS only")
    home = Path(config["home"])
    runner = Path(config["runner_dir"])
    if not (runner / ".runner").exists() or not any((runner / p).exists() for p in ("runsvc.sh", "bin/runsvc.sh")):
        raise RuntimeError("register the official runner first; .runner and bin/runsvc.sh are required")
    validate_runner_paths(runner)
    if (runner / ".service").exists():
        existing = (runner / ".service").read_text().strip()
        if existing and existing != labels(config)["runner"]:
            raise RuntimeError("existing runner service detected; stop/uninstall that service before adopting it")
    config["path"] = os.environ["PATH"]
    for tool in ("docker", "k3d", "kubectl", "terraform"):
        if not shutil.which(tool):
            raise RuntimeError(f"missing executable: {tool}")
    check_ownership(config, cluster_exists(config))
    if not state_path(config).exists():
        raise RuntimeError("provision the fresh Terraform root before installing startup services")
    # The official svc.sh performs this same copy; runsvc.sh expects the runner root as cwd.
    if not (runner / "runsvc.sh").exists():
        shutil.copy2(runner / "bin/runsvc.sh", runner / "runsvc.sh")
    # Official runsvc.sh restores PATH from this file, overriding launchd's environment.
    # Refresh the official snapshot so k3d and the selected Terraform remain available in jobs.
    (runner / ".path").write_text(config["path"] + "\n")
    (home / "bin").mkdir(parents=True, exist_ok=True, mode=0o700)
    (home / "logs").mkdir(exist_ok=True, mode=0o700)
    for source in Path(__file__).parent.glob("*.py"):
        dest = home / "bin" / source.name
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
    write_json(home / "config.json", {k: v for k, v in config.items() if k != "home"})
    agents = Path.home() / "Library/LaunchAgents"
    agents.mkdir(exist_ok=True)
    for name, body in plists(config).items():
        path = agents / f"{body['Label']}.plist"
        if path.exists():
            old = plistlib.loads(path.read_bytes())
            if old.get("Label") != body["Label"]:
                raise RuntimeError("refusing to overwrite an unrelated LaunchAgent")
        path.write_bytes(plistlib.dumps(body))
        path.chmod(0o600)
    # Our restore LaunchAgent opens Docker at login; no unsupported Docker settings-file edits.
    if start:
        start_services(config)


def validate_runner_paths(runner):
    metadata = json.loads((runner / ".runner").read_text(encoding="utf-8-sig"))
    work = Path(metadata.get("workFolder", "_work"))
    if not work.is_absolute():
        work = runner / work
    # Runner's generated `bash ... {0}` command can split a script path at whitespace.
    # Check before copying files or changing any service; our launchd paths may contain spaces.
    if any(char.isspace() for path in (runner.resolve(), work.resolve()) for char in str(path)):
        raise RuntimeError("runner and work directory paths must not contain whitespace; use a fixed path such as ~/.local/share/one-tatchi/runners/secondary")


def start_services(config):
    for label in labels(config).values():
        domain = f"gui/{os.getuid()}"
        if run(["launchctl", "print", f"{domain}/{label}"], check=False).returncode:
            run(["launchctl", "bootstrap", domain, Path.home() / f"Library/LaunchAgents/{label}.plist"])
        run(["launchctl", "kickstart", f"{domain}/{label}"])


def stop_services(config, uninstall=False):
    for label in reversed(list(labels(config).values())):
        domain = f"gui/{os.getuid()}/{label}"
        if not run(["launchctl", "print", domain], check=False).returncode:
            run(["launchctl", "bootout", domain])
            # bootout may return while runsvc.sh is still stopping its listener.
            # A following start must not mistake that terminating job for a loaded service.
            wait_for(lambda: run(["launchctl", "print", domain], check=False).returncode != 0,
                     timeout=30, interval=0.2)
        if uninstall:
            (Path.home() / f"Library/LaunchAgents/{label}.plist").unlink(missing_ok=True)
    # Never stop/delete Docker, the cluster, DB, or its state. These can be used by other work.


def wait_for(predicate, timeout=300, interval=5):
    with budget(timeout):
        while not predicate():
            pause(interval)


def boot_id():
    if sys.platform == "darwin":
        raw = run(["/usr/sbin/sysctl", "-n", "kern.boottime"]).stdout
        return "macos-" + re.search(r"sec = (\d+)", raw)[1]
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def maintenance(config):
    return (Path(config["home"]) / "maintenance.json").exists()


def kube(*args):
    return json.loads(run(["kubectl", f"--request-timeout={remaining(10):.3f}s", *args, "-o", "json"]).stdout)


def http_check(url, marker=None):
    # curl's total timeout bounds DNS, connection AND response body; never log the body.
    started = time.monotonic()
    response = run(["curl", "--silent", "--show-error", "--fail", "--proto", "=https", "--max-time",
                    str(remaining(6)), "--max-filesize", "2000000", url], check=False, timeout=remaining(7))
    return {"ok": response.returncode == 0 and (marker is None or marker in response.stdout),
            "elapsed_ms": round((time.monotonic() - started) * 1000), "curl_exit": response.returncode}


def endpoint_snapshot(config):
    result = {"boot_id": boot_id(), "observed_at": time.time(), "status": "failed", "urls": {}, "external": {}, "errors": []}
    for env in config["environments"]:
        try:
            url = resolve(f"{config['service']}-fe", env, timeout=0)
            checks = {"page": http_check(url), "api": http_check(url + "api/guestbook"),
                      "database_health": http_check(url + "health", '"database":"connected"')}
            result["external"][env] = checks
            if not all(c["ok"] for c in checks.values()):
                raise RuntimeError(f"external HTTP verification failed: {env}")
            # Only addresses verified in THIS observation are published.
            result["urls"][env] = url
        except (RuntimeError, ValueError, KeyError, subprocess.SubprocessError):
            result["errors"].append(f"current tunnel lookup or HTTP check failed: {env}")
    result["status"] = "ready" if not result["errors"] else "failed"
    result["verified_at"] = time.time()
    result["expires_at"] = result["verified_at"] + 60
    return result


def refresh_urls(config):
    home = Path(config["home"])
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (home / "urls.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        result = {"status": "failed", "observed_at": time.time(), "urls": {}, "external": {}, "errors": []}
        try:
            with budget(25):
                result["boot_id"] = boot_id()
                if maintenance(config):
                    raise RuntimeError("maintenance in progress")
                prepare_kubeconfig(config)
                result = endpoint_snapshot(config)
        except (RuntimeError, ValueError, KeyError, subprocess.SubprocessError):
            result["errors"].append("URL refresh unavailable")
        write_json(home / "endpoints.json", result)
        return result


def workloads_ready(config):
    for env in config["environments"]:
        db = kube("get", "statefulset", f"{config['service']}-db-{env}", "-n", config["secret_namespace"])
        if db.get("status", {}).get("readyReplicas", 0) != 1:
            return False
        for component in ("be", "fe"):
            rollout = kube("get", "rollout", f"{config['service']}-{component}", "-n", env)
            state = rollout.get("status", {})
            if state.get("phase") != "Healthy" or str(state.get("observedGeneration")) != str(rollout["metadata"]["generation"]):
                return False
    return True


def verify_version(config):
    expected = config.get("kubernetes_version")
    if not expected:
        return
    info = json.loads(run(["docker", "inspect", f"k3d-{config['cluster']}-server-0"]).stdout)[0]
    nodes = kube("get", "nodes")["items"]
    if info["Config"]["Image"] != "rancher/k3s:" + expected or not nodes or any(
            n["status"]["nodeInfo"]["kubeletVersion"].replace("+", "-") != expected for n in nodes):
        raise RuntimeError("live Docker/Kubernetes version differs from profile; complete the explicit image replacement first")


def restore(config):
    home = Path(config["home"])
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if maintenance(config):
        raise RuntimeError("maintenance in progress; automatic recovery is suspended")
    with (home / "operation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        record = {"status": "recovering", "cluster": config["cluster"], "started_at": time.time(), "stages": []}
        began = time.monotonic()
        phase = "docker"
        def stage(name, action):
            nonlocal phase
            phase = name
            entry = {"phase": name, "started_at": time.time(), "status": "running"}
            record["stages"].append(entry)
            record["phase"] = name
            write_json(home / "restore.json", record)
            action()
            entry.update(status="ready", finished_at=time.time())
            entry["elapsed_seconds"] = round(entry["finished_at"] - entry["started_at"], 3)
            write_json(home / "restore.json", record)
        try:
            with budget(590):
                record["boot_id"] = boot_id()
                write_json(home / "restore.json", record)
                def docker():
                    run(["open", "-g", "-a", "Docker"])
                    wait_for(lambda: run(["docker", "info"], check=False).returncode == 0)
                stage("docker", docker)
                def cluster():
                    check_ownership(config, cluster_exists(config))
                    seconds = max(1, int(remaining(120)))
                    run(["k3d", "cluster", "start", config["cluster"], "--wait", "--timeout", f"{seconds}s"], timeout=remaining(122))
                stage("cluster", cluster)
                # k3d's nginx upstream resolves the server name only when nginx starts.
                # A surviving/early-started proxy can retain the previous Docker IP.
                def proxy():
                    proxy_name = f"k3d-{config['cluster']}-serverlb"
                    info = json.loads(run(["docker", "inspect", proxy_name]).stdout)[0]
                    labels = info["Config"].get("Labels", {})
                    if labels.get("k3d.cluster") != config["cluster"] or labels.get("k3d.role") != "loadbalancer":
                        raise RuntimeError("API proxy does not belong to the configured cluster")
                    run(["docker", "restart", "-t", "10", proxy_name], timeout=remaining(25))
                stage("api-proxy", proxy)
                def api():
                    prepare_kubeconfig(config)
                    wait_for(lambda: run(["kubectl", "get", "--raw=/readyz", "--request-timeout=5s"], check=False).returncode == 0, timeout=120)
                    seconds = max(1, int(remaining(120)))
                    run(["kubectl", "wait", "--for=condition=Ready", "nodes", "--all", f"--timeout={seconds}s"], timeout=remaining(122))
                    verify_version(config)
                stage("kubernetes", api)
                def workloads():
                    def check():
                        try:
                            return workloads_ready(config)
                        except (RuntimeError, KeyError, ValueError):
                            return False
                    wait_for(check, timeout=remaining(240))
                stage("database-apps", workloads)
                def tunnels():
                    for env in config["environments"]:
                        seconds = max(1, int(remaining(120)))
                        run(["kubectl", "rollout", "status", f"deployment/cloudflared-{env}", "-n", "cloudflared", f"--timeout={seconds}s"], timeout=remaining(122))
                stage("tunnels", tunnels)
                def external():
                    def check():
                        result = endpoint_snapshot(config)
                        write_json(home / "endpoints.json", result)
                        record["external"] = result
                        return result["status"] == "ready"
                    wait_for(check, timeout=remaining(120))
                stage("external-http", external)
                record.update(status="ready", time=int(time.time()), elapsed_seconds=round(time.monotonic() - began, 3))
                write_json(home / "restore.json", record)
        except (RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            # Error messages can include command output; persist a safe class and stage only.
            record.update(status="failed", phase=phase, time=int(time.time()),
                          reason=f"{phase}: {type(exc).__name__}", elapsed_seconds=round(time.monotonic() - began, 3))
            if record["stages"]:
                record["stages"][-1].update(status="failed", finished_at=time.time())
            write_json(home / "restore.json", record)
            write_json(home / "endpoints.json", {"status": "failed", "boot_id": record.get("boot_id"), "urls": {}, "errors": [record["reason"]]})
            raise RuntimeError(record["reason"]) from None


def runner_service(config):
    if maintenance(config):
        raise RuntimeError("maintenance in progress; runner is suspended")
    def ready():
        try:
            prepare_kubeconfig(config)
            return run(["kubectl", "get", "--raw=/readyz", "--request-timeout=5s"], check=False).returncode == 0
        except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    wait_for(ready, timeout=600)
    runner = Path(config["runner_dir"])
    # GitHub requires runsvc.sh for custom services. exec lets launchd own/stop the actual service.
    os.chdir(runner)
    os.execv(str(runner / "runsvc.sh"), [str(runner / "runsvc.sh")])


def database_passwords(config):
    passwords = {}
    namespace = config["secret_namespace"]
    for env in config["environments"]:
        name = f"{config['service']}-db-{env}"
        raw = run(["kubectl", "get", "secret", f"{name}-credentials", "-n", namespace,
                   "--ignore-not-found", "-o", "json"]).stdout
        if raw.strip():
            data = json.loads(raw)["data"]
            if base64.b64decode(data["username"]).decode() != "app":
                raise RuntimeError(f"existing database username differs: {env}")
            passwords[env] = base64.b64decode(data["password"]).decode()
        else:
            resources = json.loads(run(["kubectl", "get", "statefulsets,pvc", "-n", namespace, "-o", "json"]).stdout)
            if any(name in r["metadata"]["name"] for r in resources["items"]):
                raise RuntimeError(f"database/volume exists without credentials: {env}; restore the Secret")
            passwords[env] = secrets.token_urlsafe(32)
    return passwords


def terraform(config, args):
    if not args or args[0] not in ("init", "validate", "plan", "apply", "output"):
        raise ValueError("allowed Terraform commands: init, validate, plan, apply, output")
    if any(a.startswith(("-destroy", "-replace", "-state", "-backup")) for a in args):
        raise ValueError("destructive/state overrides are not supported by this wrapper")
    targets = [a for a in args if a.startswith("-target")]
    if targets and (len(targets) != 1 or targets[0] not in ("-target=module.cluster", "-target=module.cluster_addons")):
        raise ValueError("only the two documented bootstrap targets are supported")
    # The wrapper owns identity and credentials. Do not override them with arbitrary CLI values.
    if any(a.startswith(("-var", "-chdir")) for a in args):
        raise ValueError("put non-secret settings in the root tfvars; CLI variable overrides are unsupported")
    if args[0] == "apply" and any(not a.startswith("-") for a in args[1:]):
        raise ValueError("saved-plan apply is unsupported; run plan then apply through this wrapper")
    if any(os.environ.get(key) for key in ("TF_LOG", "TF_LOG_CORE", "TF_LOG_PROVIDER", "TF_LOG_PATH")):
        raise RuntimeError("disable Terraform debug logging before handling credentials")
    env = dict(os.environ)
    env["TF_VAR_name"] = config["cluster"]
    env["TF_VAR_api_port"] = str(config["api_port"])
    if config.get("kubernetes_version"):
        env["TF_VAR_kubernetes_version"] = config["kubernetes_version"]
    root = Path(config["terraform_root"])
    if args[0] in ("plan", "apply"):
        for path in [*root.glob("*.tfvars"), *root.glob("*.tfvars.json")]:
            if re.search(r"\bonprem_(?:auth|db_passwords)\b", path.read_text()):
                raise RuntimeError(f"ephemeral credentials must not be stored in {path.name}")
        exists = cluster_exists(config)
        check_ownership(config, exists)
        bootstrap = "-target=module.cluster" in args
        if not exists and not bootstrap:
            raise RuntimeError("new root: first apply -target=module.cluster, then -target=module.cluster_addons")
        if exists:
            env["TF_VAR_onprem_auth"] = json.dumps(prepare_kubeconfig(config))
            env["KUBECONFIG"] = os.environ["KUBECONFIG"]
            if args[0] == "apply":
                verify_version(config)
            if not any(a.startswith("-target=") for a in args):
                env["TF_VAR_onprem_db_passwords"] = json.dumps(database_passwords(config))
        args = [*args, f"-var=name={config['cluster']}", f"-var=api_port={config['api_port']}"]
        if config.get("kubernetes_version"):
            args.append(f"-var=kubernetes_version={config['kubernetes_version']}")
    return subprocess.run(["terraform", f"-chdir={root}", *args], env=env).returncode


def status(config):
    with budget(60):
        return _status(config)


def _status(config):
    result = {"profile": config["profile"], "cluster": config["cluster"], "observed_at": time.time(), "urls": {}, "errors": []}
    result["boot_id"] = boot_id()
    result["maintenance"] = maintenance(config)
    if result["maintenance"]:
        result["errors"].append("maintenance in progress")
    if sys.platform == "darwin":
        result["ac_power"] = "AC Power" in run(["pmset", "-g", "batt"]).stdout
        assertions = run(["pmset", "-g", "assertions"]).stdout
        awake = run(["launchctl", "print", f"gui/{os.getuid()}/{labels(config)['awake']}"], check=False).stdout
        pid = re.search(r"\bpid = (\d+)", awake)
        result["sleep_prevented"] = bool(pid and f"pid {pid[1]}(caffeinate)" in assertions and re.search(r"PreventSystemSleep\s+1", assertions))
        result["services"] = {k: run(["launchctl", "print", f"gui/{os.getuid()}/{v}"], check=False).returncode == 0 for k, v in labels(config).items()}
        if not result["ac_power"]:
            result["errors"].append("AC power is disconnected; continuous operation is not guaranteed")
        if not all(result["services"].values()):
            result["errors"].append("one or more startup services are not loaded")
        if not result["sleep_prevented"]:
            result["errors"].append("the managed caffeinate assertion is absent")
    result["docker_ready"] = run(["docker", "info"], check=False).returncode == 0
    if result["docker_ready"]:
        try:
            check_ownership(config, cluster_exists(config))
            prepare_kubeconfig(config)
            ids = run(["docker", "ps", "-aq", "--filter", f"label=k3d.cluster={config['cluster']}"]).stdout.split()
            result["nodes"] = [{"name": c["Name"], "started": c["State"]["StartedAt"], "restarts": c["RestartCount"]}
                               for c in json.loads(run(["docker", "inspect", *ids]).stdout)] if ids else []
            result["pods"] = json.loads(run(["kubectl", "get", "pods", "-A", "-o", "json"]).stdout)
            # Only non-secret workload identity/status is returned; no pod env/spec.
            result["pods"] = [{"namespace": p["metadata"]["namespace"], "name": p["metadata"]["name"],
                               "uid": p["metadata"]["uid"], "created": p["metadata"]["creationTimestamp"],
                               "status": p["status"]} for p in result["pods"]["items"]]
            unready = [p["name"] for p in result["pods"] if p["status"].get("phase") != "Succeeded" and
                       (p["status"].get("phase") != "Running" or not p["status"].get("containerStatuses") or
                        not all(c.get("ready") for c in p["status"]["containerStatuses"]))]
            if unready:
                result["errors"].append("unready pods: " + ", ".join(unready))
            result["versions"] = {"configured": config.get("kubernetes_version"),
                "nodes": [{"name": n["metadata"]["name"], "version": n["status"]["nodeInfo"]["kubeletVersion"],
                           "addresses": n["status"]["addresses"]} for n in kube("get", "nodes")["items"]],
                "containers": [{"name": c["Name"], "image": c["Config"]["Image"],
                                "addresses": [n["IPAddress"] for n in c["NetworkSettings"]["Networks"].values()]}
                               for c in json.loads(run(["docker", "inspect", *ids]).stdout)] if ids else []}
            endpoints = endpoint_snapshot(config)
            result["urls"] = endpoints["urls"]
            result["external"] = endpoints["external"]
            result["errors"].extend(endpoints["errors"])
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            result["errors"].append(str(exc) if isinstance(exc, RuntimeError) else "cluster authentication failed")
    path = Path(config["home"]) / "restore.json"
    if path.exists():
        result["last_restore"] = json.loads(path.read_text())
        result["last_restore"]["current_boot"] = result["last_restore"].get("boot_id") == result["boot_id"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", choices=["doctor", "install", "start", "stop", "status", "terraform", "migrate-state", "uninstall", "restore", "runner", "refresh-urls"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    a = parser.parse_args()
    config = load_config(a.config)
    if a.command in ("doctor", "status"):
        result = status(config)
        print(json.dumps(result, indent=2))
        return int(not result["docker_ready"] or bool(result["errors"]))
    if a.command == "install":
        install(config)
    elif a.command == "start":
        start_services(config)
    elif a.command in ("stop", "uninstall"):
        stop_services(config, uninstall=a.command == "uninstall")
    elif a.command == "restore":
        restore(config)
    elif a.command == "refresh-urls":
        result = refresh_urls(config)
        return int(result is not None and result["status"] != "ready")
    elif a.command == "runner":
        runner_service(config)
    elif a.command == "terraform":
        return terraform(config, a.args)
    elif a.command == "migrate-state":
        from state_migration import migrate
        return migrate(config, a.args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"onprem: {exc if not isinstance(exc, subprocess.CalledProcessError) else 'credential operation failed'}", file=sys.stderr)
        sys.exit(1)
