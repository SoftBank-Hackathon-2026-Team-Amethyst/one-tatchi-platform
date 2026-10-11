#!/usr/bin/env python3
"""Read-only T26 evidence review. Never dispatches, approves, merges or deploys.

Exit codes: 0 confirmed, 1 contradictory evidence, 2 incomplete evidence.
Only timestamped output (not GitHub's echoed command blocks) proves execution.
"""

import argparse
import base64
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CONFIRMED, UNKNOWN, MISMATCH = "확인됨", "미확인", "불일치"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
STAMP = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+Z) (.*)$")
DIGEST = re.compile(r"\S+@sha256:[a-f0-9]{64}")
MARKER = re.compile(
    r"<!-- one-tatchi-approval run=(\d+) environment=prod state=approved by=(slack:\S+) -->"
)
CONFIG = re.compile(
    r"^compliance:\s*(?:none|'none'|\"none\"|regulated|'regulated'|\"regulated\")\s*(?:#.*)?$"
)


def time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None


def between(value, start, end):
    values = [time(x) for x in (value, start, end)]
    return all(x is not None for x in values) and values[1] <= values[0] <= values[2]


def parse_log(raw):
    """Retain a narrow allowlist of configuration and observed rollout/audit output."""
    env, lines, group_stack = {}, [], []
    for raw_line in raw.splitlines():
        match = STAMP.match(raw_line)
        if not match:
            continue
        stamp, message = match.groups()
        # ANSI-colored script echoes are not observations, even if the log was truncated.
        echo = "\x1b[36;1m" in message
        message = ANSI.sub("", message).rstrip()
        if message.startswith("##[group]"):
            group_stack.append(message.startswith("##[group]Run "))
            continue
        if message == "##[endgroup]":
            if group_stack:
                group_stack.pop()
            continue
        if echo:
            continue
        if any(group_stack):
            declaration = re.fullmatch(
                r"  (IMAGES|MODE|NAMESPACE|TARGET|TARGET_LABEL|VERIFY_OBSERVABILITY): (.*)", message
            )
            if declaration:
                key, value = declaration.groups()
                env.setdefault(key, set()).add(value)
            continue
        if not message.startswith("##["):
            lines.append((stamp, message))

    snapshots, audits, promotions, current, collecting_images = [], [], [], None, False
    for index, (stamp, message) in enumerate(lines):
        promotion = re.fullmatch(r"rollout '([^']+)' promoted", message)
        if promotion:
            promotions.append({"name": promotion[1], "timestamp": stamp})
        name = re.fullmatch(r"Name:\s+(\S+)", message)
        if name:
            current = {"name": name[1], "timestamp": stamp, "images": [], "stable": []}
            snapshots.append(current)
            collecting_images = False
        elif current is not None:
            if message.startswith("Namespace:"):
                current["namespace"] = message.split(":", 1)[1].strip()
            elif message.startswith("Status:"):
                status = message.split(":", 1)[1].split()
                current["phase"] = status[-1] if status else ""
            elif message.startswith("Images:"):
                collecting_images = True
            elif message.startswith("Replicas:"):
                collecting_images = False
            if collecting_images:
                image = DIGEST.search(message)
                if image:
                    current["images"].append(image[0])
                    if re.search(r"\bstable\b", message) and re.search(r"\bactive\b", message):
                        current["stable"].append(image[0])
        if message.startswith("audit log: s3://"):
            parts = []
            for _, part in lines[index + 1 : index + 30]:
                parts.append(part)
                if part.strip() == "}":
                    try:
                        record = json.loads("\n".join(parts))
                        if isinstance(record, dict):
                            audits.append(record)
                    except ValueError:
                        pass
                    break
    return {"env": env, "snapshots": snapshots, "audits": audits, "promotions": promotions}


class GitHub:
    """No generic command escape hatch: every network call is explicitly GET."""

    def __init__(self, repo):
        self.repo = repo
        self.errors = []

    def get(self, path, *, pages=False, text=False):
        command = ["gh", "api", "--hostname", "github.com", "--method", "GET", path]
        if pages:
            command += ["--paginate", "--slurp"]
        if text:
            command += ["--allow-escape-sequences"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
            if result.returncode:
                # Do not include raw CLI stderr, tokens, config contents or job logs in errors.
                raise ValueError("GitHub GET failed")
            return result.stdout if text else json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.errors.append(path)
            return "" if text else None

    def list(self, suffix):
        pages = self.get(f"repos/{self.repo}/{suffix}", pages=True)
        return [item for page in (pages or []) for item in page] if pages is not None else []

    def run(self, spec):
        run_id, _, requested_attempt = spec.partition("/")
        path = f"repos/{self.repo}/actions/runs/{run_id}"
        latest = self.get(path) if not requested_attempt else None
        attempt = int(requested_attempt or (latest or {}).get("run_attempt", 1))
        meta = self.get(f"{path}/attempts/{attempt}") or {}
        pages = self.get(f"{path}/attempts/{attempt}/jobs?per_page=100", pages=True)
        jobs = [job for page in (pages or []) for job in page.get("jobs", [])]
        for job in jobs:
            if re.search(r"(?:^| / )(deploy|rollout)$", job.get("name", "")):
                job["log"] = self.get(f"repos/{self.repo}/actions/jobs/{job['id']}/logs", text=True)
        return {"meta": meta, "jobs": jobs, "requested_id": int(run_id), "attempt": attempt}


def collect(args):
    client = GitHub(args.repo)
    result = {
        "repo": args.repo,
        "target": args.target,
        "services": args.services,
        "deploy": client.run(args.deploy_run),
    }
    for key in ("test_rollout", "prod_rollout", "yolo"):
        spec = getattr(args, key + "_run")
        if spec:
            result[key] = client.run(spec)
    if args.pr:
        result["pr"] = client.get(f"repos/{args.repo}/pulls/{args.pr}") or {}
        for name, endpoint in (
            ("comments", f"issues/{args.pr}/comments"),
            ("reviews", f"pulls/{args.pr}/reviews"),
            ("files", f"pulls/{args.pr}/files"),
        ):
            result["pr_" + name] = client.list(endpoint + "?per_page=100")
    sha = result["deploy"]["meta"].get("head_sha", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        result["approval_comments"] = client.list(f"commits/{sha}/comments?per_page=100")
        content = client.get(f"repos/{args.repo}/contents/.deploy/config.yaml?ref={sha}")
        if content and content.get("encoding") == "base64":
            try:
                config = base64.b64decode(content["content"]).decode()
                matches = [line for line in config.splitlines() if CONFIG.fullmatch(line)]
                keys = [line for line in config.splitlines() if line.startswith("compliance:")]
                if len(keys) == len(matches) == 1:
                    result["compliance"] = (
                        matches[0].split(":", 1)[1].split("#", 1)[0].strip().strip("'\"")
                    )
            except (ValueError, UnicodeError, KeyError):
                pass
    result["errors"] = client.errors
    return result


class Review:
    def __init__(self, data):
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", data["repo"])
            or ".." in data["repo"]
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["target"])
            or not data["services"]
            or len(set(data["services"])) != len(data["services"])
            or any(not re.fullmatch(r"[a-z0-9][a-z0-9-]*", s) for s in data["services"])
        ):
            raise ValueError("invalid repository, target or services")
        self.data, self.checks = data, []
        self.stable_at = {}
        self.repo = data["repo"]
        self.target = data["target"]
        self.services = data["services"]

    def add(self, name, state, detail, source=""):
        self.checks.append({"check": name, "status": state, "detail": detail, "source": source})

    def url(self, run):
        return f"https://github.com/{self.repo}/actions/runs/{run.get('requested_id')}/attempts/{run.get('attempt')}"

    def valid_run(self, run, label, workflow):
        meta = run.get("meta", {})
        valid = (
            meta.get("id") == run.get("requested_id")
            and meta.get("run_attempt") == run.get("attempt")
            and meta.get("repository", {}).get("full_name") == self.repo
            and meta.get("path", "").split("@", 1)[0] == f".github/workflows/{workflow}.yml"
        )
        self.add(
            label,
            CONFIRMED if valid else (MISMATCH if meta else UNKNOWN),
            "저장소·워크플로·실행 차수 대조",
            self.url(run),
        )
        return valid

    def job(self, run, environment, action="deploy"):
        found = []
        target = f"all@{self.target}.{environment}"
        for job in run.get("jobs", []):
            if (
                job.get("run_id") != run.get("requested_id")
                or job.get("head_sha") != run.get("meta", {}).get("head_sha")
                or job.get("run_attempt", run.get("attempt")) != run.get("attempt")
            ):
                continue
            if not re.search(rf"(?:^| / ){action}$", job.get("name", "")):
                continue
            parsed = parse_log(job.get("log", ""))
            records = [a for a in parsed["audits"] if a.get("target") == target]
            # Missing audit still permits an incomplete report for a uniquely scoped job.
            env = parsed["env"]
            scoped = env.get("NAMESPACE") == {environment} and (
                self.target in env.get("TARGET_LABEL", set())
                or (
                    not any(env.get("TARGET_LABEL", set()))
                    and self.target in env.get("TARGET", set())
                )
            )
            if records or scoped:
                found.append((job, parsed))
        return found[0] if len(found) == 1 else (None, None)

    def audit(self, run, job, parsed, environment, action):
        expected = self.url(run)
        records = [
            a
            for a in parsed["audits"]
            if a.get("action") == action and a.get("target") == f"all@{self.target}.{environment}"
        ]
        valid = [
            a
            for a in records
            if a.get("run_url") == expected
            and a.get("version") == run["meta"].get("head_sha")
            and a.get("result") == "success"
            and between(a.get("timestamp"), job.get("started_at"), job.get("completed_at"))
        ]
        self.add(
            f"{environment} {action} 감사 기록",
            CONFIRMED if len(valid) == 1 else (MISMATCH if records else UNKNOWN),
            "실제 감사 JSON의 버전·대상·시각·실행 차수 확인",
            job.get("html_url", expected),
        )
        return valid[0] if len(valid) == 1 else None

    def images(self, parsed, sha):
        values = parsed["env"].get("IMAGES", set())
        if len(values) != 1:
            return None
        try:
            images = json.loads(next(iter(values)))
            if not isinstance(images, dict) or set(images) != set(self.services):
                return None
            if any(
                not isinstance(v, dict)
                or v.get("source_sha") != sha
                or not DIGEST.fullmatch(v.get("repository", "") + "@" + v.get("digest", ""))
                for v in images.values()
            ):
                return None
            return {
                name: value["repository"] + "@" + value["digest"] for name, value in images.items()
            }
        except (ValueError, TypeError):
            return None

    def environment(self, run, environment, rollout=None):
        job, parsed = self.job(run, environment)
        url = self.url(run)
        if job is None:
            self.add(
                environment, UNKNOWN, "대상·환경을 구분할 배포 job/log가 없거나 여러 개임", url
            )
            return None, None, None
        self.add(
            f"{environment} 배포",
            CONFIRMED if job.get("conclusion") == "success" else UNKNOWN,
            f"job 결과={job.get('conclusion')} (승격 판정은 별도)",
            job.get("html_url", url),
        )
        record = self.audit(run, job, parsed, environment, "deploy")
        expected = self.images(parsed, run["meta"].get("head_sha"))
        self.add(
            f"{environment} 검사 이미지",
            CONFIRMED if expected else UNKNOWN,
            "서비스별 IMAGES 입력과 source_sha 대조 (활성 이미지의 증거는 아님)",
            job.get("html_url", url),
        )
        if parsed["env"].get("VERIFY_OBSERVABILITY") == {"true"}:
            self.add(
                environment, UNKNOWN, "실측 후 정리하는 실행은 일반 배포 완료로 판정하지 않음", url
            )
            return expected, job, record
        final = parsed
        final_job = job
        was_paused = any(s.get("phase") == "Paused" for s in parsed["snapshots"])
        if was_paused and not rollout:
            if parsed["env"].get("MODE") == {"auto"}:
                automatic = self.audit(run, job, parsed, environment, "promote")
                self.add(
                    f"{environment} 자동 승격 요청",
                    CONFIRMED
                    if automatic and automatic.get("requested_by") == "ai-judge"
                    else UNKNOWN,
                    "auto 실행의 promote 감사 요청자 확인",
                    url,
                )
            else:
                self.add(
                    f"{environment} Slack 승격 요청",
                    UNKNOWN,
                    "수동 Paused 배포는 Slack rollout 실행 근거가 필요함",
                    url,
                )
        if rollout:
            if not self.valid_run(rollout, f"{environment} 승격 실행 식별", "rollout"):
                return expected, job, record
            final_job, final = self.job(rollout, environment, "rollout")
            if final_job is None:
                self.add(
                    f"{environment} 승격",
                    UNKNOWN,
                    "대상·환경이 맞는 rollout 기록 없음",
                    self.url(rollout),
                )
                return expected, job, record
            self.add(
                f"{environment} 승격 job",
                CONFIRMED if final_job.get("conclusion") == "success" else UNKNOWN,
                f"job 결과={final_job.get('conclusion')}",
                final_job.get("html_url", self.url(rollout)),
            )
            promotion = self.audit(rollout, final_job, final, environment, "promote")
            self.add(
                f"{environment} Slack 승격 요청",
                CONFIRMED
                if promotion and str(promotion.get("requested_by", "")).startswith("slack:")
                else UNKNOWN,
                "rollout 감사 기록의 Slack 요청자 확인",
                final_job.get("html_url", self.url(rollout)),
            )
        for service in self.services:
            initial = [
                s
                for s in parsed["snapshots"]
                if s["name"] == service
                and s.get("namespace") == environment
                and s.get("phase") in ("Paused", "Healthy")
                and expected
                and expected[service] in s["images"]
                and between(s["timestamp"], job.get("started_at"), job.get("completed_at"))
            ]
            observed = [
                s
                for s in final["snapshots"]
                if s["name"] == service
                and s.get("namespace") == environment
                and between(
                    s["timestamp"], final_job.get("started_at"), final_job.get("completed_at")
                )
            ]
            state, detail = (
                UNKNOWN,
                "같은 이미지의 Green 준비와 Healthy stable/active 관측 근거 부족",
            )
            if initial and observed and expected:
                ready, stable = initial[0], observed[-1]
                commands = [
                    p
                    for p in final["promotions"]
                    if p["name"] == service
                    and between(
                        p["timestamp"], final_job.get("started_at"), final_job.get("completed_at")
                    )
                ]
                if time(stable["timestamp"]) < time(ready["timestamp"]):
                    state, detail = MISMATCH, "선택한 승격 관측이 이번 버전의 Green 준비보다 앞섬"
                elif ready["phase"] == "Paused" and not commands:
                    state, detail = UNKNOWN, "Paused 이후 실제 promote 명령 결과가 없음"
                elif ready["phase"] == "Paused" and not between(
                    commands[-1]["timestamp"], ready["timestamp"], stable["timestamp"]
                ):
                    state, detail = (
                        MISMATCH,
                        "promote 명령 시각이 Green 준비와 활성 관측 사이가 아님",
                    )
                elif stable.get("phase") == "Healthy" and len(stable["stable"]) == 1:
                    if stable["stable"][0] == expected[service]:
                        state, detail = (
                            CONFIRMED,
                            "Green 준비 이후 Healthy이며 stable/active digest 일치",
                        )
                        self.stable_at[
                            (run["requested_id"], run["attempt"], environment, service)
                        ] = stable["timestamp"]
                    else:
                        state, detail = MISMATCH, "stable/active digest가 이번 배포 이미지와 다름"
            self.add(
                f"{environment} {service} 활성 버전", state, detail, final_job.get("html_url", url)
            )
        return expected, job, record

    def approval(self, run, job, audit):
        compliance = self.data.get("compliance")
        if compliance == "none":
            self.add(
                "운영 승인", CONFIRMED, "해당 커밋 compliance=none: 승인 불필요", self.url(run)
            )
            return
        if compliance != "regulated" or not job:
            self.add(
                "운영 승인",
                UNKNOWN,
                "해당 커밋 compliance 또는 prod 실행 정보 확인 불가",
                self.url(run),
            )
            return
        valid = []
        for comment in self.data.get("approval_comments", []):
            marker = MARKER.search(comment.get("body", ""))
            if (
                marker
                and int(marker[1]) == run.get("requested_id")
                and comment.get("user", {}).get("type") == "Bot"
                and comment.get("commit_id") == run["meta"].get("head_sha")
                and between(
                    comment.get("created_at"),
                    run["meta"].get("run_started_at"),
                    job.get("started_at"),
                )
                and audit
                and audit.get("requested_by") == marker[2]
            ):
                valid.append(comment)
        self.add(
            "운영 승인",
            CONFIRMED if valid else UNKNOWN,
            "현재 시도 시작 이후·prod job 시작 이전 Slack 승인 표지와 감사 요청자 대조. 표지 자체에는 차수가 없어 이전 표지는 인정하지 않음",
            valid[-1].get("html_url", self.url(run)) if valid else self.url(run),
        )

    def trace(self, run):
        meta, pr = run["meta"], self.data.get("pr", {})
        if meta.get("event") == "workflow_dispatch":
            self.add(
                "배포 경로",
                CONFIRMED if meta.get("head_branch") == "main" else MISMATCH,
                "수동 재배포: janto 스킬 완료 증거가 아님",
                self.url(run),
            )
            return "manual"
        valid = (
            meta.get("event") == "push"
            and meta.get("head_branch") == "main"
            and pr.get("merged_at")
            and pr.get("merge_commit_sha") == meta.get("head_sha")
            and pr.get("base", {}).get("ref") == "main"
            and pr.get("base", {}).get("repo", {}).get("full_name") == self.repo
            and between(pr.get("merged_at"), "1970-01-01T00:00:00Z", meta.get("created_at"))
        )
        self.add(
            "PR → main 실행",
            CONFIRMED if valid else (MISMATCH if pr else UNKNOWN),
            "병합 커밋·기준 브랜치·실행 이벤트·시각 대조",
            pr.get("html_url", self.url(run)),
        )
        is_yolo = (
            pr.get("head", {}).get("ref", "").startswith("yolo/")
            and pr.get("head", {}).get("repo", {}).get("full_name") == self.repo
            and any(label.get("name") == "yolo" for label in pr.get("labels", []))
        )
        if is_yolo:
            yolo = self.data.get("yolo")
            if yolo and self.valid_run(yolo, "yolo 실행 식별", "deploy"):
                ym = yolo["meta"]
                linked = (
                    ym.get("event") == "push"
                    and ym.get("head_branch") == pr.get("head", {}).get("ref")
                    and ym.get("head_sha") == pr.get("head", {}).get("sha")
                )
                self.add(
                    "yolo → 병합 PR",
                    CONFIRMED if linked else MISMATCH,
                    "yolo head와 PR head를 대조. rebase 이후 main SHA는 달라도 됨",
                    self.url(yolo),
                )
                _, yolo_job, _ = self.environment(yolo, "test")
                _, parsed = self.job(yolo, "test")
                self.add(
                    "yolo 자동 승격 모드",
                    CONFIRMED if parsed and parsed["env"].get("MODE") == {"auto"} else UNKNOWN,
                    "병합 전 yolo test가 auto 모드인지 확인",
                    self.url(yolo),
                )
                ordered = yolo_job and between(
                    yolo_job.get("completed_at"), ym.get("run_started_at"), pr.get("merged_at")
                )
                self.add(
                    "yolo test → PR 병합 순서",
                    CONFIRMED if ordered else UNKNOWN,
                    "병합 이전 test job 완료 확인",
                    self.url(yolo),
                )
            else:
                self.add(
                    "yolo test", UNKNOWN, "병합 전 yolo 실행을 지정해야 함", pr.get("html_url", "")
                )
            return "yolo"
        comments = [
            c
            for c in self.data.get("pr_comments", [])
            if c.get("user", {}).get("type") == "Bot"
            and "Slack에서 `slack:" in c.get("body", "")
            and "머지했다" in c.get("body", "")
        ]
        self.add(
            "Slack PR 머지",
            CONFIRMED if comments and pr.get("merged_at") else UNKNOWN,
            "PR의 Slack 머지 댓글 확인",
            pr.get("html_url", ""),
        )
        protected = any(
            f.get("filename") in (".deploy/config.yaml", ".github/CODEOWNERS", "CODEOWNERS")
            for f in self.data.get("pr_files", [])
        )
        if protected:
            reviews = [
                r
                for r in self.data.get("pr_reviews", [])
                if r.get("state") == "APPROVED"
                and "Slack에서 `slack:" in r.get("body", "")
                and between(r.get("submitted_at"), pr.get("created_at"), pr.get("merged_at"))
            ]
            self.add(
                "Slack 코드 리뷰",
                CONFIRMED if reviews else UNKNOWN,
                "보호 파일 변경의 Slack 승인 리뷰 확인 (권한 규칙은 GitHub가 판단)",
                pr.get("html_url", ""),
            )
        return "ordinary-pr"

    def run(self):
        deploy = self.data["deploy"]
        if self.valid_run(deploy, "배포 실행 식별", "deploy"):
            route = self.trace(deploy)
            test_images, _, _ = self.environment(deploy, "test", self.data.get("test_rollout"))
            prod_images, prod_job, prod_audit = self.environment(
                deploy, "prod", self.data.get("prod_rollout")
            )
            self.add(
                "test → prod 이미지",
                CONFIRMED
                if test_images and test_images == prod_images
                else (MISMATCH if test_images and prod_images else UNKNOWN),
                "같은 main 실행 내 모든 서비스의 OCI digest 대조",
                self.url(deploy),
            )
            stable = [
                self.stable_at.get((deploy["requested_id"], deploy["attempt"], "test", service))
                for service in self.services
            ]
            starts = [
                step.get("started_at")
                for step in (prod_job or {}).get("steps", [])
                if step.get("name", "").startswith("서비스 배포")
            ]
            if all(stable) and len(starts) == 1 and time(starts[0]):
                ordered = max(time(value) for value in stable) <= time(starts[0])
                self.add(
                    "test 승격 → prod 배포 순서",
                    CONFIRMED if ordered else MISMATCH,
                    "모든 test 서비스의 stable 관측이 prod 서비스 배포 시작보다 앞서는지 확인",
                    self.url(deploy),
                )
            else:
                self.add(
                    "test 승격 → prod 배포 순서",
                    UNKNOWN,
                    "test stable 또는 prod 배포 시작 시각 증거 부족",
                    self.url(deploy),
                )
            self.approval(deploy, prod_job, prod_audit)
        else:
            route = "unknown"
        for path in self.data.get("errors", []):
            self.add("조회 누락", UNKNOWN, "GET 조회 실패: " + path)
        states = {c["status"] for c in self.checks}
        status = MISMATCH if MISMATCH in states else UNKNOWN if UNKNOWN in states else CONFIRMED
        return {
            "status": status,
            "route": route,
            "repo": self.repo,
            "target": self.target,
            "checks": self.checks,
            "limits": "지정한 과거 실행의 증거 판정이며 현재 클러스터 상태·Slack 화면·janto 스킬 호출 자체를 보증하지 않습니다.",
        }


def markdown(report):
    lines = [
        f"# T26 증거 검증: {report['status']}",
        "",
        f"저장소: {report['repo']} · 대상: {report['target']} · 경로: {report['route']}",
        "",
    ]
    for item in report["checks"]:
        source = f" [근거]({item['source']})" if item["source"] else ""
        lines.append(f"- **{item['status']} · {item['check']}**: {item['detail']}{source}")
    return "\n".join(lines + ["", report["limits"], ""])


def run_spec(value):
    if not re.fullmatch(r"[1-9]\d*(?:/[1-9]\d*)?", value):
        raise argparse.ArgumentTypeError("실행 ID 또는 실행 ID/차수를 지정하세요")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="SoftBank-Hackathon-2026-Team-Amethyst/demo-app")
    parser.add_argument("--target", default="aws")
    parser.add_argument("--services", nargs="+", default=["demo-app-be", "demo-app-fe"])
    parser.add_argument("--pr", type=int)
    parser.add_argument("--deploy-run", type=run_spec)
    for name in ("test-rollout", "prod-rollout", "yolo"):
        parser.add_argument(f"--{name}-run", type=run_spec)
    parser.add_argument("--fixture", type=Path, help="offline API/log fixture; no network requests")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo) or ".." in args.repo:
        parser.error("잘못된 repository")
    if not args.fixture and not args.deploy_run:
        parser.error("--deploy-run 또는 --fixture가 필요합니다")
    if len(set(args.services)) != len(args.services):
        parser.error("서비스 이름을 중복 지정할 수 없습니다")
    try:
        data = json.loads(args.fixture.read_text()) if args.fixture else collect(args)
        report = Review(data).run()
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        print(
            f"증거 형식을 읽지 못했습니다 ({type(error).__name__}). 원본을 확인하세요.",
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.format == "json"
        else markdown(report)
    )
    return {CONFIRMED: 0, MISMATCH: 1, UNKNOWN: 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
