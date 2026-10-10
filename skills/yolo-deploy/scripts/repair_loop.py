#!/usr/bin/env python3
"""Track one yolo deployment and guard up to three repair commits (Git + gh)."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

MAX_REPAIRS = 3
SOURCE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
                   ".vue", ".svelte", ".html", ".css", ".scss", ".sass", ".go",
                   ".rs", ".java", ".kt", ".kts", ".rb", ".php", ".c", ".h",
                   ".cpp", ".hpp", ".cs", ".sql", ".sh"}
PROTECTED_PARTS = {".git", ".github", ".deploy", "node_modules", "vendor", "coverage",
                   "test", "tests", "__tests__", "spec", "specs", "fixture", "fixtures",
                   "__fixtures__", "__snapshots__", "e2e", "smoke"}
PROTECTED_NAMES = {"codeowners", "package.json", "pyproject.toml", "setup.py", "setup.cfg",
                   "conftest.py", "tox.ini", "pytest.ini", "makefile", "cmakelists.txt",
                   ".dockerignore", "docker-compose.yml", "compose.yaml"}
RUN_FIELDS = "databaseId,headSha,headBranch,event,workflowDatabaseId,attempt,status,conclusion,url"


class Stop(Exception):
    pass


def command(args, cwd, timeout=60, allow_failure=False):
    try:
        result = subprocess.run(args, cwd=cwd, env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"},
                                text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise Stop(f"명령 시간 초과: {args[0]} {args[1] if len(args) > 1 else ''}") from exc
    except OSError as exc:
        raise Stop(f"명령 실행 실패: {args[0]} ({exc})") from exc
    if result.returncode and not allow_failure:
        # Raw logs stay local; do not copy potentially sensitive command output into reports.
        raise Stop(f"명령 실패 ({result.returncode}): {' '.join(args[:3])}")
    return result


def git(root, *args, **kwargs):
    return command(["git", *args], root, **kwargs).stdout.strip()


def normalized(path):
    p = PurePosixPath(path)
    if not path or p.is_absolute() or any(x in ("", ".", "..") for x in path.split("/")):
        raise Stop(f"저장소 상대 경로가 필요함: {path!r}")
    return p.as_posix()


def within(path, root):
    return path == root or path.startswith(root + "/")


def protected(path):
    p = PurePosixPath(path.lower())
    name = p.name
    return (bool(set(p.parts) & PROTECTED_PARTS) or name in PROTECTED_NAMES
            or bool(re.search(r"(^test[_\-.]|[_\-.](test|spec)([_\-.]|$)|\.snap$)", name))
            or name.startswith(("eslint", ".eslint", "ruff", ".ruff", "tsconfig", "jsconfig",
                                "biome", "jest", "vitest", "vite.config", "webpack", "babel",
                                ".babel", "karma", ".trivy", ".gitleaks", "requirements"))
            or name.endswith((".lock", "-lock.json", "-lock.yaml", ".lockb"))
            or ".config." in name)


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)) as out:
        out.write(text)
    os.replace(tmp, path)


class Session:
    def __init__(self, root):
        self.root = Path(git(root, "rev-parse", "--show-toplevel"))
        self.branch = git(self.root, "branch", "--show-current")
        if not self.branch.startswith("yolo/"):
            raise Stop("현재 브랜치는 yolo/로 시작해야 함")
        key = hashlib.sha256(self.branch.encode()).hexdigest()[:20]
        self.directory = Path(git(self.root, "rev-parse", "--git-path", f"yolo-deploy/{key}"))
        if not self.directory.is_absolute():
            self.directory = self.root / self.directory
        self.path = self.directory / "state.json"
        self.state = None

    @contextmanager
    def lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.directory / "lock", "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Stop("같은 브랜치의 도구가 이미 실행 중임") from exc
            yield

    def load(self):
        try:
            state = json.loads(self.path.read_text())
            valid = (state["version"] == 1 and state["branch"] == self.branch
                     and state["origin"] == git(self.root, "remote", "get-url", "origin")
                     and type(state["repairs"]) is int and 0 <= state["repairs"] <= MAX_REPAIRS
                     and state["repairs"] == len(state["history"])
                     and re.fullmatch(r"[0-9a-f]{40,64}", state["initial_sha"])
                     and re.fullmatch(r"[0-9a-f]{40,64}", state["sha"])
                     and state["sources"] and state["checks"]
                     and state["history_file"].startswith(".deploy/log/")
                     and isinstance(state["workflow_id"], int)
                     and state["status"] in {"ready", "watching", "checks_failed", "committing",
                                              "pending_push", "waiting_merge", "complete", "stopped"})
            if not valid:
                raise ValueError("invalid state")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise Stop("실행 상태가 없거나 불명확함. 재초기화하지 말고 상태를 확인할 것") from exc
        self.state = state

    def save(self):
        private_write(self.path, json.dumps(self.state, ensure_ascii=False, indent=2) + "\n")

    def gh(self, *args, **kwargs):
        return command(["gh", *args], self.root, **kwargs)

    def gh_json(self, *args):
        try:
            return json.loads(self.gh(*args).stdout)
        except ValueError as exc:
            raise Stop("GitHub 응답이 올바른 JSON이 아님") from exc

    def remote_sha(self, missing_ok=False):
        lines = git(self.root, "ls-remote", "--heads", "origin", f"refs/heads/{self.branch}").splitlines()
        if not lines and missing_ok:
            return None
        if len(lines) != 1:
            raise Stop("원격 yolo 브랜치를 하나로 확인할 수 없음")
        return lines[0].split()[0]

    def head(self):
        return git(self.root, "rev-parse", "HEAD")

    def clean(self):
        return not git(self.root, "status", "--porcelain", "--untracked-files=all")

    def init(self, args):
        if self.path.exists():
            self.load()
            for option, key in ((args.source, "sources"), (args.dockerfile, "dockerfiles"),
                                (args.value, "values"), (args.protect, "protected")):
                if option and sorted(option) != self.state[key]:
                    raise Stop("기존 실행의 수정 범위는 변경할 수 없음")
            if args.check and [json.loads(x) for x in args.check] != self.state["checks"]:
                raise Stop("기존 실행의 로컬 검사 명령은 변경할 수 없음")
            return
        # A remaining session artifact with no state must never reset the budget.
        if any(p.name != "lock" for p in self.directory.iterdir()):
            raise Stop("이전 실행 흔적은 있지만 상태가 없음. 횟수를 초기화할 수 없음")
        if not args.source or not args.check:
            raise Stop("최초 init에는 --source와 JSON 배열 형식 --check가 필요함")
        if not self.clean():
            raise Stop("최초 push 직후 깨끗한 작업 트리에서 init할 것")
        sha = self.head()
        if self.remote_sha() != sha:
            raise Stop("최초 커밋이 원격 브랜치와 다름. 먼저 초기 push를 확인할 것")
        scopes = {}
        for key, items in (("sources", args.source), ("dockerfiles", args.dockerfile),
                           ("values", args.value), ("protected", args.protect)):
            scopes[key] = sorted({normalized(p) for p in items})
            for p in scopes[key]:
                self.no_links(p)
                if not (self.root / p).exists():
                    raise Stop(f"초기 범위 경로가 없음: {p}")
        for path in scopes["sources"]:
            if protected(path) or path.split("/")[0] in {"deploy", "infra", "scripts"}:
                raise Stop(f"앱 소스 범위로 지정할 수 없음: {path}")
        for path in scopes["dockerfiles"]:
            if PurePosixPath(path).name != "Dockerfile" or protected(path):
                raise Stop(f"서비스 Dockerfile만 지정 가능: {path}")
        for path in scopes["values"]:
            p = PurePosixPath(path)
            helm = path.startswith("deploy/") and p.name.startswith("values") and p.suffix in {".yaml", ".yml"}
            tf = path.startswith("infra/envs/") and p.suffix == ".tfvars"
            if not (helm or tf) or protected(path):
                raise Stop(f"Helm values 또는 Terraform tfvars만 지정 가능: {path}")
        try:
            checks = [json.loads(x) for x in args.check]
            if not all(isinstance(c, list) and c and all(isinstance(a, str) and a for a in c) for c in checks):
                raise ValueError("invalid check")
        except ValueError as exc:
            raise Stop("--check는 비어 있지 않은 명령 인자 JSON 배열이어야 함") from exc
        origin = git(self.root, "remote", "get-url", "origin")
        repo = self.gh_json("repo", "view", origin, "--json", "nameWithOwner")["nameWithOwner"]
        workflow = self.gh_json("api", f"repos/{repo}/actions/workflows/deploy.yml")
        if workflow["path"] != ".github/workflows/deploy.yml":
            raise Stop("deploy.yml 워크플로 경로가 다름")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        history_file = f".deploy/log/{stamp}-{sha[:8]}-yolo.md"
        if (self.root / history_file).exists():
            raise Stop("실행 기록 경로가 이미 존재함")
        self.state = {"version": 1, "repo": repo, "origin": origin, "branch": self.branch,
                      "initial_sha": sha, "sha": sha, "workflow_id": workflow["id"],
                      "repairs": 0, "history": [], "checks": checks, "history_file": history_file,
                      "status": "ready", "reason": "초기 push 관찰 대기", "runs": [], **scopes}
        private_write(self.directory / "started", sha + "\n")
        self.save()

    def no_links(self, path):
        for part in [PurePosixPath(path), *PurePosixPath(path).parents]:
            if (self.root / str(part)).is_symlink():
                raise Stop(f"심볼릭 링크는 수정 범위로 사용할 수 없음: {path}")

    def allowed(self, path):
        normalized(path)
        self.no_links(path)
        if protected(path) or any(within(path, p) for p in self.state["protected"]):
            return False
        if path in self.state["dockerfiles"] or path in self.state["values"]:
            return True
        return (PurePosixPath(path).suffix.lower() in SOURCE_SUFFIXES
                and any(within(path, p) for p in self.state["sources"]))

    def names(self, *args):
        out = command(["git", *args], self.root).stdout
        return set(filter(None, out.split("\0")))

    def changed(self):
        return (self.names("diff", "--no-renames", "--name-only", "-z")
                | self.names("diff", "--cached", "--no-renames", "--name-only", "-z")
                | self.names("ls-files", "--others", "--exclude-standard", "-z"))

    def history_text(self):
        lines = ["# yolo 자동 수정 이력", "", f"- 초기 커밋: `{self.state['initial_sha']}`",
                 f"- 브랜치: `{self.branch}`", ""]
        for item in self.state["history"]:
            lines += [f"## 수정 {item['number']}", f"- 실패 실행: {item['run']['url']}",
                      f"- 실패 커밋: `{item['parent']}`", f"- 원인과 수정: {item['reason']}",
                      "- 파일: " + ", ".join(f"`{p}`" for p in item["files"]),
                      "- 로컬 검사: 모두 통과", ""]
        return "\n".join(lines) + "\n"

    def guard(self, expected, generated=False):
        if self.head() != self.state["sha"]:
            raise Stop("예상하지 않은 로컬 커밋. 자동 rebase/amend 없이 중단")
        changed = self.changed()
        history_file = self.state["history_file"]
        required = set(expected) | ({history_file} if generated else set())
        if changed != required:
            raise Stop(f"지정한 수정 파일과 실제 변경이 다름: {sorted(changed ^ required)}")
        # Inspect both sides of renames, the index, worktree and cumulative commits.
        cumulative = self.names("diff", "--no-renames", "--name-only", "-z",
                                self.state["initial_sha"], "HEAD")
        for path in sorted(changed | cumulative):
            if path == history_file:
                self.no_links(path)
                if (self.root / path).read_text() != self.history_text():
                    raise Stop("도구가 생성한 실행 기록이 변경됨")
            elif not self.allowed(path):
                raise Stop(f"보호 경로 또는 허용 범위 밖 변경: {path}")
            for rev in (self.state["initial_sha"], "HEAD"):
                entry = git(self.root, "ls-tree", rev, "--", path)
                if entry.startswith(("120000", "160000")):
                    raise Stop(f"링크 또는 서브모듈 변경: {path}")
            entries = git(self.root, "ls-files", "--stage", "--", path)
            if any(e.startswith(("120000", "160000")) for e in entries.splitlines()):
                raise Stop(f"staged 링크 또는 서브모듈 변경: {path}")

    def verify_run(self, run):
        s = self.state
        if (run["headSha"] != s["sha"] or run["headBranch"] != self.branch
                or run["event"] != "push" or run["workflowDatabaseId"] != s["workflow_id"]):
            raise Stop("GitHub 실행이 저장소·브랜치·SHA·워크플로 조건과 다름")

    def view(self, run):
        data = self.gh_json("run", "view", str(run["databaseId"]), "--repo", self.state["repo"],
                            "--json", RUN_FIELDS + ",jobs")
        self.verify_run(data)
        if data["databaseId"] != run["databaseId"] or data["attempt"] != run["attempt"]:
            raise Stop("실행 ID 또는 attempt가 바뀜. 다른 실행 결과로 수정하지 않음")
        return data

    @staticmethod
    def classify(run):
        jobs = run["jobs"]
        if run["status"] != "completed" or run["conclusion"] not in {"success", "failure"}:
            return "stopped", "실행 취소·대기·시간 초과·시작 오류 또는 알 수 없는 결과"
        if any(j["status"] != "completed" or j["conclusion"] not in {"success", "failure", "skipped"} for j in jobs):
            return "stopped", "완료되지 않았거나 비정상 종료한 job이 있음"
        failed = [j for j in jobs if j["conclusion"] == "failure"]
        checks = [j for j in jobs if j["name"].startswith("checks / ")]
        if any(not j["name"].startswith("checks / ") for j in failed):
            return "stopped", "배포 또는 검사 외 job 실패: 자동 수정 대상이 아님"
        if failed and run["conclusion"] == "failure":
            return "checks_failed", "검사 실패: 허용 범위의 앱 수정 가능"
        if (run["conclusion"] == "success" and checks
                and any(j["conclusion"] == "success" for j in checks)
                and any(j["name"].startswith("test / deploy") and j["conclusion"] == "success" for j in jobs)):
            return "complete", "검사와 test 배포 job 성공. 트래픽 승격 여부는 별도 확인"
        return "stopped", "검사·test 배포 완료를 확인할 수 없음"

    def observe_merge(self, attempts=5, interval=10):
        """Observe one PR without requesting merge or changing the remote branch."""
        pr = self.state.get("pull_request")
        for attempt in range(attempts):
            if pr:
                pr = self.gh_json("pr", "view", pr["url"], "--repo", self.state["repo"],
                                  "--json", "url,state,headRefOid")
            else:
                pulls = self.gh_json("pr", "list", "--repo", self.state["repo"], "--head", self.branch,
                                     "--base", "main", "--state", "all", "--limit", "100",
                                     "--json", "url,state,headRefOid")
                matches = [p for p in pulls if p["headRefOid"] == self.state["sha"]]
                if len(matches) != 1:
                    raise Stop("T8 자동 PR을 관찰한 SHA와 연결할 수 없음")
                pr = matches[0]
            if pr["headRefOid"] != self.state["sha"]:
                raise Stop("관찰 중 PR head가 변경됨. 이전 검증으로 머지 완료 처리하지 않음")
            remote = self.remote_sha(missing_ok=True)
            if remote not in {None, self.state["sha"]}:
                raise Stop("관찰 중 원격 브랜치가 변경됨")
            self.state["pull_request"] = pr
            if remote is None and pr["state"] != "MERGED":
                raise Stop("원격 브랜치가 삭제됐지만 해당 SHA의 T8 머지를 확인할 수 없음")
            if pr["state"] == "MERGED":
                return "complete", "검사·test 배포 성공 및 같은 SHA의 main PR 머지 확인"
            if pr["state"] == "CLOSED":
                return "stopped", "main PR이 머지되지 않고 닫힘"
            if pr["state"] != "OPEN":
                raise Stop("알 수 없는 PR 상태")
            if attempt + 1 < attempts:
                time.sleep(interval)
        return "waiting_merge", "자동 머지 요청 후 PR이 열려 있음. 리뷰·검사·충돌 상태 확인 필요"

    def watch(self, discovery_seconds=120, watch_seconds=5400, poll_seconds=5,
              merge_poll_seconds=10):
        if self.state["status"] in {"committing", "pending_push"}:
            raise Stop("미완료 commit/push 상태를 먼저 확인할 것")
        if (self.head() != self.state["sha"] or not self.clean()
                or self.remote_sha(missing_ok=True) not in {None, self.state["sha"]}):
            raise Stop("로컬·원격 커밋 또는 작업 트리가 예상 상태와 다름")
        if self.state["status"] == "waiting_merge":
            # Resume the saved PR; do not rediscover or rerun the completed Actions run.
            status, reason = self.observe_merge(interval=merge_poll_seconds)
            self.state.update(status=status, reason=reason)
            self.save()
            return
        deadline = time.monotonic() + discovery_seconds
        while True:
            candidates = self.gh_json("run", "list", "--repo", self.state["repo"], "--workflow", "deploy.yml",
                                      "--branch", self.branch, "--commit", self.state["sha"], "--event", "push",
                                      "--limit", "20", "--json", RUN_FIELDS)
            matches = []
            for run in candidates:
                try:
                    self.verify_run(run)
                    matches.append(run)
                except Stop:
                    continue
            if len(matches) > 1:
                raise Stop("조건에 맞는 실행이 여러 개여서 선택할 수 없음")
            if matches:
                break
            if time.monotonic() >= deadline:
                raise Stop("2분 이내에 push SHA의 실행을 찾지 못함")
            time.sleep(min(poll_seconds, max(0, deadline - time.monotonic())))
        run = matches[0]
        self.state.update(status="watching", run=run, reason="선택한 실행 관찰 중")
        self.save()
        self.gh("run", "watch", str(run["databaseId"]), "--repo", self.state["repo"],
                "--exit-status", "--compact", timeout=watch_seconds, allow_failure=True)
        data = self.view(run)
        status, reason = self.classify(data)
        remote = self.remote_sha(missing_ok=True)
        if remote not in {None, self.state["sha"]}:
            raise Stop("관찰 중 원격 브랜치가 변경됨")
        yolo_pr = any(j["name"].split(" / ")[-1] == "yolo-pr" and j["conclusion"] == "success"
                      for j in data["jobs"])
        if status == "complete" and yolo_pr:
            status, reason = self.observe_merge(interval=merge_poll_seconds)
        elif remote is None:
            raise Stop("원격 브랜치가 삭제됐지만 해당 SHA의 T8 머지를 확인할 수 없음")
        if data["conclusion"] != "success":
            logs = self.gh("run", "view", str(run["databaseId"]), "--repo", self.state["repo"],
                           "--attempt", str(run["attempt"]), "--log-failed").stdout
            if status == "checks_failed" and not logs.strip():
                raise Stop("실패 로그가 없어 원인을 확인할 수 없음")
            log_path = self.directory / f"{run['databaseId']}-{run['attempt']}.log"
            private_write(log_path, logs)
            data["log_path"] = str(log_path)
        if status == "checks_failed" and self.state["repairs"] >= MAX_REPAIRS:
            status, reason = "stopped", "수정 3회 소진. 남은 검사 실패를 사람에게 보고"
        self.state.update(status=status, reason=reason, run=data)
        self.state["runs"].append(data)
        self.save()

    def push_pending(self):
        s = self.state
        if self.head() != s["sha"] or not self.clean():
            raise Stop("push 대기 커밋 또는 작업 트리가 변경됨")
        remote = self.remote_sha()
        if remote not in {s["sha"], s["history"][-1]["parent"]}:
            raise Stop("다른 작업자가 원격 브랜치를 갱신함")
        if remote != s["sha"]:
            git(self.root, "push", "origin", f"HEAD:refs/heads/{self.branch}", timeout=120)
        if self.remote_sha() != s["sha"]:
            raise Stop("push 후 원격 SHA를 확인하지 못함")
        s.update(status="ready", reason="수정 push 완료. 새 SHA 관찰 대기")
        self.save()

    def retry(self, args):
        if self.state["status"] == "pending_push":
            self.push_pending()
            return
        if self.state["status"] != "checks_failed" or self.state["repairs"] >= MAX_REPAIRS:
            raise Stop("확인된 검사 실패와 남은 수정 횟수가 있어야 retry 가능")
        if not args.reason or not args.file:
            raise Stop("--reason과 실제 수정 파일을 --file로 지정할 것")
        files = sorted({normalized(p) for p in args.file})
        data = self.view(self.state["run"])
        if self.classify(data)[0] != "checks_failed":
            raise Stop("검사 실패 상태가 변경됨")
        if self.remote_sha() != self.state["sha"]:
            raise Stop("원격 브랜치가 변경됨")
        self.guard(files)
        for i, check in enumerate(self.state["checks"]):
            result = command(check, self.root, timeout=600, allow_failure=True)
            private_write(self.directory / f"local-{self.state['repairs'] + 1}-{i}.log",
                          result.stdout + result.stderr)
            if result.returncode:
                raise Stop(f"로컬 검사 {i + 1} 실패. 커밋·push하지 않음")
        self.guard(files)
        if self.remote_sha() != self.state["sha"]:
            raise Stop("로컬 검사 중 원격 브랜치가 변경됨")
        number = self.state["repairs"] + 1
        self.state["history"].append({"number": number, "parent": self.state["sha"],
                                      "files": files, "reason": args.reason,
                                      "run": {k: data[k] for k in ("databaseId", "attempt", "url")}})
        self.state.update(repairs=number, status="committing", reason="수정 커밋 생성 중")
        self.save()
        record = self.root / self.state["history_file"]
        self.no_links(self.state["history_file"])
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(self.history_text())
        self.guard(files, generated=True)
        git(self.root, "add", "--", *files, self.state["history_file"])
        expected_tree = git(self.root, "write-tree")
        parent = self.state["sha"]
        git(self.root, "commit", "-m", f"[yolo] 검사 실패 자동 수정 {number}/3",
            "-m", args.reason)
        sha = self.head()
        if (git(self.root, "rev-parse", "HEAD^") != parent
                or git(self.root, "rev-parse", "HEAD^{tree}") != expected_tree or not self.clean()):
            raise Stop("커밋 결과가 검증한 변경과 다름. push하지 않음")
        self.state["history"][-1]["sha"] = sha
        self.state.update(sha=sha, status="pending_push", reason="수정 커밋 생성 완료, push 대기")
        self.save()
        self.push_pending()

    def report(self):
        s = self.state
        run = s.get("run", {})
        return {"status": s["status"], "reason": s["reason"], "repo": s["repo"],
                "branch": s["branch"], "sha": s["sha"], "repairs": s["repairs"],
                "remaining": MAX_REPAIRS - s["repairs"], "history": s["history"],
                "run_url": run.get("url"), "run_sha": run.get("headSha"),
                "run_attempt": run.get("attempt"), "log_path": run.get("log_path"),
                "pull_request": s.get("pull_request"),
                "jobs": [{"name": j["name"], "conclusion": j["conclusion"]} for j in run.get("jobs", [])],
                "promotion": "not_verified", "state_path": str(self.path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="대상 앱 저장소 경로")
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init")
    for flag in ("source", "dockerfile", "value", "protect", "check"):
        init.add_argument("--" + flag, action="append", default=[])
    commands.add_parser("watch")
    retry = commands.add_parser("retry")
    retry.add_argument("--reason")
    retry.add_argument("--file", action="append", default=[])
    commands.add_parser("report")
    args = parser.parse_args()
    try:
        session = Session(Path(args.repo).resolve())
        with session.lock():
            try:
                if args.action == "init":
                    session.init(args)
                else:
                    session.load()
                    if args.action == "watch":
                        session.watch()
                    elif args.action == "retry":
                        session.retry(args)
            except (Stop, KeyError, TypeError, ValueError, OSError) as exc:
                # Preserve the phase, particularly an interrupted commit/push, under the lock.
                if session.state is not None:
                    session.state["reason"] = str(exc)
                    session.save()
                    report = session.report()
                    report["error"] = str(exc)
                    print(json.dumps(report, ensure_ascii=False, indent=2))
                    return 1
                raise
            print(json.dumps(session.report(), ensure_ascii=False, indent=2))
    except (Stop, KeyError, TypeError, ValueError, OSError) as exc:
        print(json.dumps({"status": "stopped", "error": str(exc)}, ensure_ascii=False))
        return 1
    return 1 if session.state["status"] == "stopped" else 0


if __name__ == "__main__":
    sys.exit(main())
