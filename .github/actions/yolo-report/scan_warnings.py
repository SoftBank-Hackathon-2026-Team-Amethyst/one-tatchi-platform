#!/usr/bin/env python3
"""배포를 막지 않은 경고를 모은다 (T10). 결과 파일은 collect.py --warnings 입력이다.

checks.yml은 HIGH 이상(수정판이 있는 것)만 막는다. 여기서는 막지 않은 것을 기록한다.
  - 취약점: UNKNOWN · LOW · MEDIUM, 그리고 수정판이 없어 막지 않은 HIGH · CRITICAL
  - IaC 설정: UNKNOWN · LOW · MEDIUM
  - 라이선스: MEDIUM (HIGH 이상은 checks가 막는다. LOW · UNKNOWN은 일반 라이선스라 뺀다)
  - 검사 예외: .trivyignore 항목과 위의 사유 주석
yolo 브랜치가 갈라진 지점(base)도 같은 방식으로 스캔해, 이 브랜치가 새로 들여온 경고에 new_on_branch를 붙인다.
스캔이 하나라도 실패하면 status=failed로 남긴다(collect.py가 수집 실패로 처리한다).
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

NON_BLOCKING = {"UNKNOWN", "LOW", "MEDIUM"}
TITLE_LIMIT = 300


class ScanError(Exception):
    pass


def clip(text, limit=TITLE_LIMIT):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def run(cmd, cwd=None):
    try:
        return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise ScanError(f"{cmd[0]} 실행 파일이 없다") from None
    except subprocess.CalledProcessError as exc:
        lines = (exc.stderr or "").strip().splitlines()
        raise ScanError(f"{' '.join(cmd[:3])} 실패: {lines[-1] if lines else exc.returncode}") from None


def trivy(binary, tree, scanners, path, output):
    """tree 안에서 그 트리의 .trivyignore를 적용해 스캔한다. 경로가 없으면 빈 결과."""
    target = Path(tree) / path
    if not target.exists():
        return {"Results": []}
    cmd = [binary, "fs", "--quiet", "--scanners", scanners, "--format", "json", "--output", str(output)]
    ignore = Path(tree) / ".trivyignore"
    if ignore.is_file():
        cmd += ["--ignorefile", str(ignore)]
    run(cmd + [path], cwd=tree)
    try:
        return json.loads(Path(output).read_text())
    except (OSError, ValueError):
        raise ScanError(f"trivy {scanners} 결과를 읽지 못했다") from None


def findings(vuln_report, misconfig_report):
    items = []
    for result in vuln_report.get("Results") or []:
        target = result.get("Target") or "?"
        for v in result.get("Vulnerabilities") or []:
            sev = v.get("Severity", "UNKNOWN")
            if sev in NON_BLOCKING or not v.get("FixedVersion"):
                title = v.get("Title") or v["VulnerabilityID"]
                if sev not in NON_BLOCKING:
                    title = f"수정판 없음: {title}"
                items.append({"source": "vulnerability", "severity": sev, "id": v["VulnerabilityID"],
                              "target": target, "package": v.get("PkgName"), "title": clip(title)})
        for lic in result.get("Licenses") or []:
            if lic.get("Severity") == "MEDIUM":
                items.append({"source": "license", "severity": "MEDIUM", "id": lic.get("Name") or "?",
                              "target": lic.get("FilePath") or target, "package": lic.get("PkgName"),
                              "title": clip(f"{lic.get('Category', '')} 라이선스 {lic.get('Name', '')}".strip())})
    for result in misconfig_report.get("Results") or []:
        target = result.get("Target") or "?"
        for m in result.get("Misconfigurations") or []:
            if m.get("Status", "FAIL") == "FAIL" and m.get("Severity", "UNKNOWN") in NON_BLOCKING:
                items.append({"source": "misconfiguration", "severity": m.get("Severity", "UNKNOWN"),
                              "id": m["ID"], "target": target, "package": None,
                              "title": clip(m.get("Title") or m["ID"])})
    return items


def exceptions(tree):
    """.trivyignore 항목. 빈 줄 없이 바로 위에 붙은 주석 묶음이 사유다(연달은 항목은 같은 사유를 쓴다)."""
    path = Path(tree) / ".trivyignore"
    if not path.is_file():
        return []
    items, comment, entries_since_comment = [], [], False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            comment, entries_since_comment = [], False
        elif stripped.startswith("#"):
            if entries_since_comment:
                comment, entries_since_comment = [], False
            comment.append(stripped.lstrip("#").strip())
        else:
            entry = stripped.split()[0]
            entries_since_comment = True
            items.append({"source": "scan_exception", "severity": "UNKNOWN", "id": entry,
                          "target": ".trivyignore", "package": None,
                          "title": clip(" ".join(comment) or "사유 주석 없음")})
    return items


def key(item):
    return (item["source"], item["id"], item["target"], item["package"])


def scan_tree(binary, tree, scan_path, iac_path, work, label):
    vuln = trivy(binary, tree, "vuln,license", scan_path, Path(work) / f"{label}-vuln.json")
    misconfig = trivy(binary, tree, "misconfig", iac_path, Path(work) / f"{label}-misconfig.json") \
        if iac_path else {"Results": []}
    return findings(vuln, misconfig) + exceptions(tree)


def scanner_info(binary):
    data = json.loads(run([binary, "version", "--format", "json"]))
    updated = (data.get("VulnerabilityDB") or {}).get("UpdatedAt")
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", updated or "")
    return {"name": "trivy", "version": data.get("Version", "?"), "db_updated_at": m.group(1) + "Z" if m else None}


def collect(args):
    repo = Path(args.repo_root).resolve()
    work = Path(tempfile.mkdtemp(prefix="yolo-warnings-"))
    base_tree = work / "base"
    try:
        base = run(["git", "-C", str(repo), "merge-base", args.sha, args.base_ref]).strip()
        run(["git", "-C", str(repo), "worktree", "add", "--quiet", "--detach", str(base_tree), base])
        head_items = scan_tree(args.trivy, repo, args.scan_path, args.iac_path, work, "head")
        base_keys = {key(i) for i in scan_tree(args.trivy, base_tree, args.scan_path, args.iac_path, work, "base")}
        for item in head_items:
            item["new_on_branch"] = key(item) not in base_keys
        return {"status": "ok", "detail": None, "base_sha": base,
                "scanner": scanner_info(args.trivy), "items": head_items}
    finally:
        if base_tree.exists():
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(base_tree)],
                           capture_output=True)
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--repo-root", default=".", help="배포한 커밋을 전체 이력으로 checkout한 대상 레포")
    p.add_argument("--sha", default=os.environ.get("GITHUB_SHA"), required=not os.environ.get("GITHUB_SHA"))
    p.add_argument("--base-ref", default="origin/main")
    p.add_argument("--scan-path", default=".", help="checks.yml scan-path와 같게")
    p.add_argument("--iac-path", default="", help="checks.yml iac-path와 같게. 비우면 IaC 경고를 모으지 않는다")
    p.add_argument("--trivy", default=os.environ.get("TRIVY", "trivy"))
    args = p.parse_args(argv)
    try:
        result = collect(args)
        new = sum(1 for i in result["items"] if i["new_on_branch"])
        print(f"비차단 경고 {len(result['items'])}건 (이 브랜치에서 새로 생김 {new}건)")
    except (ScanError, KeyError, TypeError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, ScanError) else f"경고 결과 형식 오류: {type(exc).__name__}"
        result = {"status": "failed", "detail": clip(detail), "base_sha": None, "scanner": None, "items": []}
        print(f"::warning::비차단 경고 수집 실패: {result['detail']}")
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
