#!/usr/bin/env python3
"""Unified Feishu inbound agent — routing + agent-client analysis in one pass.

Replaces the former Layer 2A (triage_agent.py) + Layer 2B split. Scans open
feishu-inbound issues, applies deterministic routing, runs deep analysis via
AgentClient (OpenCode), updates labels/assignee, and posts a combined comment.

Usage:
    python tools/feishu_inbound/inbound_agent.py --legacy
    python tools/feishu_inbound/inbound_agent.py --legacy --issue 441
    python tools/feishu_inbound/inbound_agent.py --legacy --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import re
import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
_ASP_ROOT = _SCRIPT_DIR.parent.parent
_STATE_FILE = _ASP_ROOT / "state" / "feishu_inbound_agent_state.json"
_ANALYSIS_MARKER = "## Feishu Inbound Analysis"

sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))
from routing import (  # noqa: E402
    REPO as _CENTRAL_REPO,
    format_routing_section,
    load_config,
    preflight_routing,
    run_gh,
)

# inbound_agent operates on surface repos (execution issues), not the central repo.
REPO = "AI-MYG/asp-backend"
from sync_worktrees import SyncReport, sync_asp_worktrees, surfaces_to_sync  # noqa: E402

try:
    from tools.agent_client import AgentClient
except ImportError:
    AgentClient = None  # type: ignore[misc, assignment]

# Worktree root for code analysis (the workspace containing projects/asp/*)
_WORKTREE_ROOT = Path(
    os.getenv("ASP_WORKTREE_ROOT", str(Path.home() / "CursorWorks" / "rootgrove"))
).resolve()

_ASP_CONTEXT_BASE = """
## ASP 代码库（必须先阅读再写结论）

- **Monorepo 路径**: `projects/asp/`（→ AndroidStudioProject）
- **分析前已执行 worktree sync**：各 surface 的 base 分支已与 `origin` 对齐（见 `workflow_feishu_inbound_agent.md`）
- **Worktree / Surface**（见 `projects/asp/AGENTS.md`）:
  - backend: `backend/app/`（routers, services, models, schemas, migrations）
  - app: `inputbaby_app/inputbaby_app/lib/`
  - admin: `nativesense-admin/nativesense-admin/src/`
  - wecom: `wecom_frontend/src/`
  - websites: `websites/`

**分析前**：在对应 surface 目录检索 Issue 关键词（API 路径、模型名、页面/widget 名），打开并阅读相关文件。
"""


def _build_asp_context(stale_surfaces: list[str] | None = None) -> str:
    ctx = _ASP_CONTEXT_BASE
    if stale_surfaces:
        warning = "\n".join(
            f"- **{s}**: 本地有未提交改动，已 fetch remote refs 但未 checkout。代码可能不是最新，Evidence 需注明可能偏差。"
            for s in stale_surfaces
        )
        ctx += f"\n**Stale Warning（以下 surface 代码可能不是最新）：**\n{warning}\n"
    return ctx

INBOUND_PROMPT = """
你是 ASP 负责该 surface 的开发者 Agent。你的输出将写入 GitHub Issue comment，并作为下游执行 Agent 的**唯一指令**。
规范 SSOT: `skills/workflow_triage_routing.md`
ASP Debug（平台/环境/问题类别 + Evidence Gate）: `skills/contract_debug_analysis.md`

## 硬性规则（违反即失败）

1. **禁止技术假设**：除「必须 SSH 生产服务器做数据变更且本地无法验证」外，所有技术结论必须来自你在 `projects/asp/` 中**已阅读**的代码。每条结论附 evidence：`文件路径:行号或符号名`。禁止「根因假设」「可能」「或许」「待验证」。
2. **唯一方案**：只输出**一条**推荐实现路径。禁止方案 A/B、多选一、alternatives、「也可以考虑」。方案审核是 Human 的工作，你只交付最优解。
3. **最小 effort**：数据过滤/聚合/大列表加工优先 **backend**（直接访问 DB/API）；Flutter/Vue 只做展示。禁止把本可在后端一次完成的加工推到前端。
4. **固定执行路径**：实现必须使用 git worktree 对应 surface、分支 `issue-{{number}}/{{primary_surface}}`、提 PR：
   `python tools/smart_pr.py --issue {{number}} --surface {{primary_surface}}`
   不要在 comment 中讨论其他 git/PR 流程。
5. **待确认**：仅**产品口径**歧义（需求矛盾、业务规则不清）可列「待确认（产品）」并注明走 `workflow_asp_pr_review_feedback` 私信需求负责人。技术定位问题不得列为待确认——你必须自己读代码解决。
6. **禁止输出分析过程**：不要输出 Goal / Progress / Next Steps / 思考过程 / 「现在我来…」；**只**输出下方 8 个正式章节。

## 待处理 Issue #{number}

- **Title**: {title}
- **URL**: {url}
- **Labels**: {labels}
- **Primary surface（PR 用）**: {primary_surface}
- **Author**: {author}

### Issue 描述

{body}
{comments}

{routing_section}

{asp_context}

## 输出（Markdown，严格按章节）

### 1. 需求概述
2-3 句，仅复述 Issue 事实。

### 2. 问题分类
从以下三类中选**唯一一项**，写明分类和一句依据：
- **操作问题**: 用户操作方式不对、理解有误、配置错误等，系统行为符合预期。→ 在下方给出操作指导即可，无需改代码。
- **数据问题**: 数据库/COS/配置中的数据需要修复或补充，代码逻辑本身正确。→ 给出具体修复 SQL/脚本/操作步骤，等人工授权后执行。
- **功能问题**: 需要修改代码逻辑才能解决。→ 按完整推荐方案输出，触发下游 Agent 实现。

### 3. 去重判断
完全重复 / 部分相关 / 无重复 + 理由。

### 4. 影响模块（Evidence）
- `path/to/file.ext:line或符号` — 说明
（至少 2 条来自实际阅读的代码引用）

### 5. 根因（Evidence）
基于已读代码的数据流/逻辑结论。禁止假设性措辞。

### 6. 推荐方案（唯一）
**若为操作问题**: 给出正确的操作步骤/使用说明，说明为何当前行为是预期的。
**若为数据问题**: 给出具体修复命令（SQL/脚本/API 调用），标注需人工确认后执行。
**若为功能问题**:
1. 具体步骤（有序列表）
2. **改动文件**: 完整路径列表
3. **为何是该 surface / 为何不在前端做数据加工**: 一句（最小 effort 依据）

### 7. 执行路径
**操作问题**: 写「无需执行，已在上方给出操作指导」。
**数据问题**: 写具体执行环境（SSH/API/脚本路径），标注「需人工授权」。
**功能问题**:
- **Worktree 目录**: （对应 surface 的路径）
- **分支**: `issue-{number}/{primary_surface}`
- **提 PR**: `python tools/smart_pr.py --issue {number} --surface {primary_surface}`

### 8. Scope
S/M/L + 一句依据

### 9. 三角分工
| 角色 | 本 issue 具体产出 |
|------|-------------------|
| Human | 审核上文「推荐方案」；合并后验收 |
| Agent | 在 worktree 按推荐方案实现并 Smart PR |
| Script | CI/回归/部署脚本（如适用） |

### 待确认（产品）
（无则写「无」。有则列问题 + 将私信谁确认）

直接输出 Markdown，不要前言后语。
"""


def _load_env() -> None:
    env_file = _ASP_ROOT / ".env"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v


def _gh_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def _comments_count(issue: dict[str, Any]) -> int:
    comments = issue.get("comments", 0)
    if isinstance(comments, list):
        return len(comments)
    return int(comments or 0)


def fetch_feishu_inbound_issues(issue_number: int | None = None) -> list[dict[str, Any]]:
    if issue_number:
        raw = run_gh(
            "issue", "view", str(issue_number),
            "-R", REPO,
            "--json", "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author",
        )
        issue = json.loads(raw)
        labels = [lb["name"] for lb in issue.get("labels", [])]
        if "feishu-inbound" not in labels:
            raise ValueError(f"Issue #{issue_number} does not have feishu-inbound label")
        if issue.get("state") != "OPEN":
            raise ValueError(f"Issue #{issue_number} is not open")
        return [issue]

    raw = run_gh(
        "issue", "list",
        "-R", REPO,
        "--label", "feishu-inbound",
        "--state", "open",
        "--json", "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author",
        "--limit", "30",
    )
    return json.loads(raw)


def fetch_issue_comments(token: str, issue_number: int, max_comments: int = 30) -> list[dict[str, str]]:
    owner, repo = REPO.split("/")
    comments: list[dict[str, str]] = []
    page = 1
    while len(comments) < max_comments:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers=_gh_headers(token),
            params={"per_page": min(100, max_comments - len(comments)), "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for c in batch:
            comments.append({
                "author": c.get("user", {}).get("login", "unknown"),
                "created_at": c.get("created_at", ""),
                "body": c.get("body", "") or "",
            })
        if len(batch) < 100:
            break
        page += 1
    return comments


def _issue_comments(issue: dict[str, Any], token: str) -> list[dict[str, str]]:
    embedded = issue.get("comments")
    if isinstance(embedded, list) and embedded:
        return [
            {
                "author": (c.get("author") or {}).get("login", "unknown"),
                "created_at": c.get("createdAt", ""),
                "body": c.get("body", "") or "",
            }
            for c in embedded
        ]
    if _comments_count(issue) > 0:
        return fetch_issue_comments(token, issue["number"])
    return []


def format_comments_for_prompt(comments: list[dict[str, str]]) -> str:
    if not comments:
        return ""
    parts = ["\n### Issue Comments\n"]
    for i, c in enumerate(comments, 1):
        parts.append(f"**Comment #{i}** by `{c['author']}` at {c['created_at']}:\n")
        body = c["body"].strip()
        if len(body) > 2000:
            body = body[:2000] + "\n...(truncated)"
        parts.append(body + "\n")
    return "\n".join(parts)


def has_analysis_comment(comments: list[dict[str, str]]) -> bool:
    return any(_ANALYSIS_MARKER in (c.get("body") or "") for c in comments)


def load_state() -> dict[str, Any]:
    if _STATE_FILE.exists():
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict[str, Any]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def should_process(issue: dict[str, Any], state_entry: dict[str, Any] | None, force: bool) -> bool:
    if force:
        return True
    if state_entry and state_entry.get("last_analyzed_at"):
        issue_updated = issue.get("updatedAt") or issue.get("updated_at") or ""
        last_known = state_entry.get("last_issue_updated_at", "")
        if issue_updated and last_known and issue_updated <= last_known:
            return False
    return True


def _is_valid_analysis(text: str, issue_title: str = "") -> bool:
    """Reject agent planning dumps and semantically irrelevant output."""
    if not text or len(text.strip()) < 200:
        return False
    lowered = text.lower()
    # Accept both Chinese and English numbered section headers (##/### with 1.)
    has_section = any(marker in text for marker in ("### 1.", "## 1.", "### 1、", "## 1、"))
    if not has_section:
        return False
    junk_markers = (
        "## progress", "## goal", "## next steps",
        "now i ", "现在我来", "让我来", "让我生成",
        "我对代码库有了足够", "now let me",
    )
    if any(m in lowered for m in junk_markers):
        return False
    if issue_title:
        import re
        tokens = [w for w in re.split(r'[\s\[\]()（）:：/\-_,，。、；;！!？?]+', issue_title) if len(w) >= 2]
        # For CJK text that doesn't split well, extract 3-char sliding windows
        candidates = set()
        for t in tokens:
            candidates.add(t.lower())
            if len(t) > 3:
                for i in range(len(t) - 2):
                    candidates.add(t[i:i + 3].lower())
        if candidates and not any(c in lowered for c in candidates):
            return False
    return True


_FINALIZE_PROMPT = (
    "你已完成代码阅读和分析。现在将你的分析结果**严格**按以下 9 章节格式重新输出。\n\n"
    "格式要求（违反即失败）：\n"
    "- 第一行必须是 `### 1. 需求概述`\n"
    "- 依次输出 ### 1. 到 ### 9. 共 9 个章节（含「### 2. 问题分类」必须写明：操作问题/数据问题/功能问题）\n"
    "- 禁止 Goal/Progress/Next Steps/思考过程/英文计划块\n"
    "- 禁止在章节前加任何前言或解释\n"
    "- 直接输出 Markdown，从 `### 1. 需求概述` 开始\n"
)


# ---------------------------------------------------------------------------
# Issue classification extraction
# ---------------------------------------------------------------------------
ISSUE_TYPE_OPERATIONAL = "operational"
ISSUE_TYPE_DATA = "data"
ISSUE_TYPE_FEATURE = "feature"

_TYPE_KEYWORDS = {
    ISSUE_TYPE_OPERATIONAL: ("操作问题",),
    ISSUE_TYPE_DATA: ("数据问题",),
    ISSUE_TYPE_FEATURE: ("功能问题",),
}


def extract_issue_type(analysis_text: str) -> str:
    """Extract issue classification from '### 2. 问题分类' section."""
    # Find section 2 content
    m = re.search(r"###\s*2\.\s*问题分类\s*\n([\s\S]*?)(?=\n###\s|\Z)", analysis_text)
    if not m:
        return ISSUE_TYPE_FEATURE  # default: treat as feature if missing
    section = m.group(1).strip().lower()
    for type_key, keywords in _TYPE_KEYWORDS.items():
        if any(kw in section for kw in keywords):
            return type_key
    return ISSUE_TYPE_FEATURE


def _build_inbound_prompt(
    issue: dict[str, Any],
    routing_section: str,
    comments_md: str,
    primary_surface: str,
    stale_surfaces: list[str] | None = None,
) -> str:
    number = issue["number"]
    title = issue.get("title", "")
    labels_str = ", ".join(lb["name"] for lb in issue.get("labels", [])) or "none"
    author = (issue.get("author") or {}).get("login", "unknown")
    return INBOUND_PROMPT.format(
        number=number,
        title=title,
        url=issue.get("url", ""),
        labels=labels_str,
        primary_surface=primary_surface,
        author=author,
        body=issue.get("body", "") or "(no description)",
        comments=comments_md,
        routing_section=routing_section,
        asp_context=_build_asp_context(stale_surfaces),
    )


def analyze_via_agent_client(
    issue: dict[str, Any],
    routing_section: str,
    comments_md: str,
    primary_surface: str,
    stale_surfaces: list[str] | None = None,
) -> str | None:
    if AgentClient is None:
        print("  Error: AgentClient not importable")
        return None

    prompt = _build_inbound_prompt(issue, routing_section, comments_md, primary_surface, stale_surfaces)
    intent = os.getenv("AGENT_CLIENT_INTENT", "analysis")
    timeout = int(os.getenv("AGENT_CLIENT_TIMEOUT", "3600"))

    print(f"  Analyzing via AgentClient (intent={intent})...")
    result = AgentClient().run(
        prompt,
        intent=intent,
        workdir=_WORKTREE_ROOT,
        timeout_sec=timeout,
        validate=_is_valid_analysis,
        finalize_prompt=_FINALIZE_PROMPT,
    )

    if result.status != "success":
        print(f"  Analysis failed: {result.error}")
        return None

    print(f"  Route: {result.executor}/{result.model or 'default'} ({result.elapsed_sec}s)")
    return result.text


def apply_github_updates(number: int, routing: dict[str, Any], dry_run: bool) -> None:
    labels = routing["labels"] + ["triaged"]
    assignee = routing.get("assignee")

    if dry_run:
        print(f"  [DRY RUN] labels={labels}, assignee={assignee}")
        return

    for label in labels:
        try:
            run_gh("issue", "edit", str(number), "-R", REPO, "--add-label", label)
        except RuntimeError as e:
            print(f"  Warning: could not add label '{label}': {e}")

    if assignee:
        try:
            run_gh("issue", "edit", str(number), "-R", REPO, "--add-assignee", assignee)
        except RuntimeError as e:
            print(f"  Warning: could not assign '{assignee}': {e}")


def post_analysis_comment(number: int, routing_md: str, analysis_md: str, dry_run: bool) -> None:
    body = (
        f"{routing_md}\n\n"
        f"---\n\n"
        f"{_ANALYSIS_MARKER}\n\n"
        f"{analysis_md}\n\n"
        f"---\n"
        f"_Auto-processed by `inbound_agent.py`._"
    )
    if dry_run:
        print(f"\n{'='*60}\n[DRY RUN] Comment for #{number}:\n{'='*60}\n{body[:1500]}...")
        return
    run_gh("issue", "comment", str(number), "-R", REPO, "--body", body)


def process_issue(
    issue: dict[str, Any],
    *,
    token: str,
    dry_run: bool,
    skip_email: bool,
    force: bool,
    config: dict[str, Any],
    state: dict[str, Any],
    now_iso: str,
    stale_surfaces: list[str] | None = None,
) -> bool:
    number = issue["number"]
    key = str(number)
    title = issue.get("title", "")

    print(f"\n{'='*60}")
    print(f"Issue #{number}: {title}")
    print(f"{'='*60}")

    comments: list[dict[str, str]] = _issue_comments(issue, token)

    if has_analysis_comment(comments) and not force:
        print("  Skipping: analysis comment already exists (use --force to re-run)")
        return False

    entry = state.get(key)
    if not should_process(issue, entry, force):
        print("  Skipping: unchanged since last analysis")
        return False

    routing = preflight_routing(issue, config)
    routing_md = format_routing_section(routing)
    surfaces = routing["surfaces"]
    primary_surface = surfaces[0] if surfaces else "backend"
    print(f"  Surfaces: {routing['surfaces'] or 'NONE'}")
    print(f"  Scope: {routing['scope']}")
    print(f"  Assignee: {routing['assignee_name'] or 'NONE'}")

    comments_md = format_comments_for_prompt(comments)

    if dry_run:
        analysis_md = (
            "*(Dry-run — agent client skipped)*\n\n"
            f"**Body preview**:\n\n{(issue.get('body') or '')[:500]}"
        )
    else:
        analysis_md = analyze_via_agent_client(
            issue, routing_md, comments_md, primary_surface, stale_surfaces
        )
        if not analysis_md:
            print("  Analysis failed, will retry next cycle")
            return False

    apply_github_updates(number, routing, dry_run=dry_run)
    post_analysis_comment(number, routing_md, analysis_md, dry_run=dry_run)

    if dry_run:
        return True

    if key not in state:
        state[key] = {}
    state[key].update({
        "last_seen_at": now_iso,
        "last_analyzed_at": now_iso,
        "last_issue_updated_at": issue.get("updatedAt") or issue.get("updated_at", ""),
        "last_state": issue.get("state", "OPEN").lower(),
        "title": title,
        "url": issue.get("url", ""),
        "surfaces": routing["surfaces"],
        "assignee": routing.get("assignee"),
    })
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="[DEPRECATED] Unified agent — use triage_agent.py + issue_scanner.py"
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Run deprecated combined triage+analysis (not recommended)",
    )
    parser.add_argument("--issue", type=int, help="Process a specific issue number")
    parser.add_argument("--dry-run", action="store_true", help="Skip OpenCode, GitHub writes, and email")
    parser.add_argument("--scan-only", action="store_true", help="List candidates only")
    parser.add_argument("--skip-email", action="store_true", help="Do not send email report")
    parser.add_argument("--force", action="store_true", help="Re-analyze even if already processed")
    parser.add_argument("--skip-sync", action="store_true", help="Skip git worktree sync (not recommended)")
    parser.add_argument("--batch", type=int, default=3, help="Max issues to process per run (default: 3)")
    args = parser.parse_args()

    if not args.legacy:
        print(
            "inbound_agent.py is deprecated.\n"
            "  Pipeline B (triage):  python tools/feishu_inbound/triage_agent.py\n"
            "  Pipeline C (analyze): python tools/feishu_inbound/issue_scanner.py\n"
            "  Legacy combined run:  add --legacy\n",
            file=sys.stderr,
        )
        sys.exit(2)

    _load_env()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not set")
        sys.exit(1)

    config = load_config()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        issues = fetch_feishu_inbound_issues(args.issue)
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    issues.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
    if not args.issue and not args.scan_only and not args.dry_run:
        issues = issues[:args.batch]

    print(f"Found {len(issues)} feishu-inbound issue(s)")

    state = load_state()
    candidates: list[dict[str, Any]] = []
    for issue in issues:
        number = issue["number"]
        comments_count = _comments_count(issue)
        if comments_count > 0:
            try:
                comments = _issue_comments(issue, token)
                if has_analysis_comment(comments) and not args.force:
                    print(f"  #{number}: already analyzed")
                    continue
            except Exception:
                pass
        entry = state.get(str(number))
        if should_process(issue, entry, args.force):
            candidates.append(issue)
        else:
            print(f"  #{number}: unchanged since last run")

    print(f"  {len(candidates)} need processing")

    if args.scan_only:
        for issue in candidates:
            routing = preflight_routing(issue, config)
            print(
                f"  #{issue['number']}: surfaces={routing['surfaces']} "
                f"scope={routing['scope']} assignee={routing['assignee_name']}"
            )
        return

    if not candidates:
        print("Nothing to process.")
        return

    if not args.dry_run and AgentClient is None:
        print("Error: AgentClient not importable (tools/agent_client.py)")
        sys.exit(1)

    stale_surfaces: list[str] = []
    if not args.dry_run and not args.skip_sync:
        operator = os.getenv("GITHUB_ASSIGNEE", "369795172")
        first_routing = preflight_routing(candidates[0], config)
        first_surfaces = first_routing["surfaces"]
        primary = first_surfaces[0] if first_surfaces else "backend"
        required = surfaces_to_sync([primary])
        print(f"Syncing required surfaces {required} (operator={operator})...")
        report = sync_asp_worktrees(required, operator=operator)
        stale_surfaces = report.stale_surfaces
        if stale_surfaces:
            print(f"  Stale surfaces (proceeding with warning): {', '.join(stale_surfaces)}")

    processed = 0
    for issue in candidates:
        if process_issue(
            issue,
            token=token,
            dry_run=args.dry_run,
            skip_email=args.skip_email,
            force=args.force,
            config=config,
            state=state,
            now_iso=now_iso,
            stale_surfaces=stale_surfaces or None,
        ):
            processed += 1

    save_state(state)
    print(f"\nDone. Processed {processed} issue(s).")


if __name__ == "__main__":
    main()
