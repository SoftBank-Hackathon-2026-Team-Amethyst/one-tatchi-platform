"""docs/tasks.md를 기준으로 GitHub 이슈와 프로젝트 보드를 맞춘다.

사람은 tasks.md만 고친다. 이 스크립트는 매번 tasks.md 전체를 읽어
작업(T번호)마다 이슈의 제목 · 본문 · 라벨 · 담당자와 보드 상태를 다시 맞춘다.
그래서 할 일이 바뀌거나 다른 작업으로 옮겨져도 다음 실행에서 그대로 반영된다.

    python scripts/sync_tasks.py            # 반영
    python scripts/sync_tasks.py --dry-run  # 바뀔 내용만 출력

필요: gh CLI, GH_TOKEN(이슈 쓰기 + 조직 프로젝트 쓰기 권한).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

OWNER = "SoftBank-Hackathon-2026-Team-Amethyst"
REPO = f"{OWNER}/one-tatchi-platform"
PROJECT_NUMBER = 1
TASKS = "docs/tasks.md"

LOGINS = {
    "원가연": "silano08",
    "이소울": "soulee-dev",
    "김형래": "hyeongrae-kim",
    "배준범": "baejun10",
    "배규태": "baekyutae",
}
AREAS = {
    "레포 · 인프라": "area:infra",
    "파이프라인": "area:pipeline",
    "스킬": "area:skill",
    "관측 · 문서 · 데모": "area:docs",
}
# 스크립트가 관리하는 라벨. 이 접두사의 라벨은 tasks.md 값으로 덮어쓴다.
MANAGED = ("P0", "P1", "P2", "stage:", "area:")


@dataclass
class Task:
    id: str
    title: str
    stage: str
    prio: str = ""
    area: str = ""
    owner: str = ""
    why: str = ""
    make: str = ""
    goal: str = ""
    done: str = ""
    refs: str = ""
    deps: list[str] = field(default_factory=list)
    succ: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return sum(s.startswith("- [x]") for s in self.steps)


def run(*args: str, input: str | None = None) -> str:
    r = subprocess.run(args, capture_output=True, text=True, input=input)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:4])}: {r.stderr.strip()}")
    return r.stdout


def gql(query: str, **variables) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        args += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    return json.loads(run(*args))["data"]


def warn(msg: str) -> None:
    # GitHub Actions에서는 실행 화면에 경고로 보인다.
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"경고: {msg}")


def ids(text: str) -> list[str]:
    return re.findall(r"`(T\d+)`", text)


def parse(path: str) -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    stage = ""
    cur: Task | None = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if m := re.match(r"## (\d+)단계", line):
            stage, cur = m.group(1), None
        elif line.startswith("## "):
            stage, cur = "", None
        elif m := re.match(r"### \[(T\d+)\] (.+)", line):
            cur = Task(m.group(1), m.group(2).strip(), stage) if stage else None
            if cur:
                tasks[cur.id] = cur
        elif cur is None:
            continue
        elif line.startswith("**어디에 필요** "):
            cur.why = line.split("** ", 1)[1]
        elif line.startswith("**만들 것** "):
            cur.make = line.split("** ", 1)[1]
        elif line.startswith("**목표** "):
            cur.goal = line.split("** ", 1)[1]
        elif line.startswith("**완료 기준** "):
            cur.done = line.split("** ", 1)[1]
        elif line.startswith("- **우선순위**"):
            cur.prio = re.search(r"(P\d)", line).group(1)
            cur.area = re.search(r"\*\*영역\*\* (.+?) · \*\*담당\*\*", line).group(1).strip()
            cur.owner = re.search(r"\*\*담당\*\* (.+)$", line).group(1).strip()
        elif line.startswith("- **선행**"):
            dep, rest = line.split("**후속**", 1)
            succ, _, refs = rest.partition("**설계 문서**")
            cur.deps, cur.succ, cur.refs = ids(dep), ids(succ), refs.strip()
        elif re.match(r"- \[[ x]\] ", line):
            cur.steps.append(line)
    return tasks


def body(t: Task, num: dict[str, int]) -> str:
    def link(ts: list[str]) -> str:
        return ", ".join(f"#{num[x]} {x}" if x in num else x for x in ts) or "없음"

    return f"""**어디에 필요** {t.why}

**만들 것** {t.make}

## 목표
{t.goal}

## 할 일
{chr(10).join(t.steps)}

## 완료 기준
{t.done}

## 관계
- 선행: {link(t.deps)}
- 후속: {link(t.succ)}
- 담당: {t.owner} · 단계 {t.stage} · 우선순위 {t.prio} · 설계 문서 {t.refs}

> 이 본문은 `docs/tasks.md`에서 자동으로 만든다. 고칠 때는 tasks.md를 고친다.
"""


def labels(t: Task) -> set[str]:
    area = next((v for k, v in AREAS.items() if t.area.startswith(k)), None)
    return {t.prio, f"stage:{t.stage}"} | ({area} if area else set())


def want_status(t: Task, now: str | None) -> str | None:
    """열린 이슈의 체크 상태로 보드 상태를 정한다. 사람이 고른 Ready · In review는 되도록 그대로 둔다."""
    total, k = len(t.steps), t.checked
    if total and k == total:
        return "Done"
    if k > 0:
        return None if now in ("In progress", "In review") else "In progress"
    if now in (None, "Done"):
        return "Backlog"
    return None


class Board:
    def __init__(self) -> None:
        d = gql(
            """query($o:String!,$n:Int!){organization(login:$o){projectV2(number:$n){id
            fields(first:50){nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}
            items(first:100){nodes{id content{... on Issue{number repository{nameWithOwner}}}
            fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}""",
            o=OWNER,
            n=PROJECT_NUMBER,
        )["organization"]["projectV2"]
        self.id = d["id"]
        status = next(f for f in d["fields"]["nodes"] if f and f.get("name") == "Status")
        self.field = status["id"]
        self.options = {o["name"]: o["id"] for o in status["options"]}
        self.items: dict[int, tuple[str, str | None]] = {}
        for it in d["items"]["nodes"]:
            c = it["content"] or {}
            if c.get("repository", {}).get("nameWithOwner") == REPO:
                v = it["fieldValueByName"]
                self.items[c["number"]] = (it["id"], v["name"] if v else None)

    def status(self, number: int) -> str | None:
        return self.items.get(number, (None, None))[1]

    def set(self, number: int, node_id: str, name: str) -> None:
        item = self.items.get(number, (None, None))[0]
        if item is None:
            item = gql(
                "mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}",
                p=self.id,
                c=node_id,
            )["addProjectV2ItemById"]["item"]["id"]
        gql(
            """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){updateProjectV2ItemFieldValue(input:
            {projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$o}}){projectV2Item{id}}}""",
            p=self.id,
            i=item,
            f=self.field,
            o=self.options[name],
        )
        self.items[number] = (item, name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-board", action="store_true", help="보드는 건너뛰고 이슈만 맞춘다")
    a = ap.parse_args()

    tasks = parse(TASKS)
    issues = json.loads(
        run("gh", "issue", "list", "-R", REPO, "--state", "all", "--limit", "500",
            "--json", "number,id,title,body,state,labels,assignees")
    )
    by_id: dict[str, dict] = {}
    for i in issues:
        if m := re.match(r"\[(T\d+)\]", i["title"]):
            by_id.setdefault(m.group(1), i)

    # 1) 새 작업은 이슈부터 만든다 (본문의 관계 링크에 번호가 필요하다)
    for t in tasks.values():
        if t.id not in by_id:
            print(f"{t.id}: 새 이슈")
            if not a.dry_run:
                url = run("gh", "issue", "create", "-R", REPO, "--title", f"[{t.id}][{t.prio}] {t.title}",
                          "--body", "(tasks.md에서 생성 중)").strip()
                n = int(url.rsplit("/", 1)[1])
                node = json.loads(run("gh", "issue", "view", str(n), "-R", REPO, "--json", "id"))["id"]
                by_id[t.id] = {"number": n, "id": node, "title": "", "body": "", "state": "OPEN",
                               "labels": [], "assignees": []}
    num = {k: v["number"] for k, v in by_id.items()}

    board = None if a.no_board else Board()

    # 2) 이슈 제목 · 본문 · 라벨 · 담당자 · 열림 상태 · 보드
    for t in sorted(tasks.values(), key=lambda x: int(x.id[1:])):
        i = by_id.get(t.id)
        if i is None:  # dry-run에서 새 작업
            continue
        n = i["number"]
        changes: list[str] = []
        args = ["gh", "issue", "edit", str(n), "-R", REPO]

        title = f"[{t.id}][{t.prio}] {t.title}"
        if i["title"] != title:
            args += ["--title", title]
            changes.append("제목")
        new_body = body(t, num)
        if (i["body"] or "").strip() != new_body.strip():
            args += ["--body-file", "-"]
            changes.append(f"본문({t.checked}/{len(t.steps)})")

        have = {l["name"] for l in i["labels"]}
        managed = {l for l in have if l.startswith(MANAGED)}
        want = labels(t)
        if want - have:
            args += ["--add-label", ",".join(sorted(want - have))]
        if managed - want:
            args += ["--remove-label", ",".join(sorted(managed - want))]
        if want != managed:
            changes.append("라벨")

        # 담당자는 비어 있을 때만 채운다. GitHub에서 바꾼 담당은 덮어쓰지 않고 알린다.
        login = LOGINS.get(t.owner)
        assigned = {x["login"] for x in i["assignees"]}
        if login and not assigned:
            args += ["--add-assignee", login]
            changes.append("담당")
        elif login and login not in assigned:
            warn(f"{t.id} #{n}: 담당이 다름 (tasks.md {t.owner}, GitHub {', '.join(sorted(assigned))}). tasks.md를 고칠 것")

        if len(args) > 6 and not a.dry_run:
            run(*args, input=new_body)

        closed = i["state"] == "CLOSED"
        all_done = bool(t.steps) and t.checked == len(t.steps)
        if closed:
            # 사람이 닫은 이슈는 다시 열지 않고 보드도 건드리지 않는다.
            if not all_done:
                warn(f"{t.id} #{n}: 이슈는 닫혔는데 tasks.md에 남은 할 일 {len(t.steps) - t.checked}개. 체크하거나 이슈를 다시 열 것")
        else:
            status = board.status(n) if board else None
            target = want_status(t, status) if board else None
            if target:
                changes.append(f"보드 {status or '없음'} → {target}")
                if not a.dry_run:
                    board.set(n, i["id"], target)
            if all_done:
                changes.append("이슈 닫기")
                if not a.dry_run:
                    run("gh", "issue", "close", str(n), "-R", REPO, "--reason", "completed",
                        "--comment", "tasks.md의 할 일이 모두 체크되어 자동으로 닫음")

        if changes:
            print(f"{t.id} #{n}: {', '.join(changes)}")

    # 3) tasks.md에서 사라진 작업은 건드리지 않고 알리기만 한다
    for k, i in by_id.items():
        if k not in tasks and i["state"] == "OPEN":
            warn(f"{k} #{i['number']}: tasks.md에 없음 (그대로 둠, 필요하면 직접 닫기)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
