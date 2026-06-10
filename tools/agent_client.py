"""Simplified AgentClient for ASP — local-first coding agent.

Default backend is the local ``claude`` CLI (Claude Code in headless mode), so
ASP needs no external OpenCode Server or rootgrove ``opencode_job.py``. The
legacy OpenCode path is kept and selectable via ``ASP_AGENT_BACKEND=opencode``.

Usage:
    from tools.agent_client import AgentClient
    result = AgentClient().run(prompt, intent="analysis", workdir="/path/to/workdir")

Backend selection:
    ASP_AGENT_BACKEND=claude    # default — local `claude -p` headless
    ASP_AGENT_BACKEND=cursor    # team uses Cursor — local `cursor-agent -p`
                                #   ⚠️ 无头模式需真实 TTY，仅适合手动跑，不适合后台定时任务
    ASP_AGENT_BACKEND=opencode  # legacy — spawn rootgrove opencode_job.py

换 AI 只改 .env 一行 ASP_AGENT_BACKEND，无需改代码。各后端的实现见 _run_claude /
_run_cursor / _run_opencode，三者返回同一个 (status, text, error) 契约。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

_ASP_ROOT = Path(__file__).resolve().parent.parent
_WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", str(_ASP_ROOT.parent.parent)))

# Which coding-agent backend to drive. Local `claude` CLI by default.
_BACKEND = os.environ.get("ASP_AGENT_BACKEND", "claude").strip().lower()



@dataclass
class AgentRunResult:
    status: Literal["success", "failed", "timeout"]
    text: str
    executor: str
    model: str | None
    intent: str
    elapsed_sec: int
    error: str | None = None
    raw_output: str = ""


def _extract_last_assistant_block(text: str) -> str:
    pattern = re.compile(
        r"--- assistant ---\n([\s\S]*?)(?=\n--- |\n========== end transcript ==========\n|\Z)"
    )
    matches = pattern.findall(text)
    if matches:
        return matches[-1].strip()
    return ""


def _claude_bin() -> str:
    """Resolve the local claude CLI path."""
    return os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude") or "claude"


def _claude_env() -> dict[str, str]:
    """Env for the claude subprocess.

    On Windows the CLI requires CLAUDE_CODE_GIT_BASH_PATH pointing at bash.exe;
    auto-detect a git-bash if the var isn't already set so the call works
    out-of-the-box.
    """
    env = dict(os.environ)
    if sys.platform == "win32" and not env.get("CLAUDE_CODE_GIT_BASH_PATH"):
        for cand in (
            r"D:\Git\bin\bash.exe",
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ):
            if Path(cand).exists():
                env["CLAUDE_CODE_GIT_BASH_PATH"] = cand
                break
    return env


def _run_claude(
    prompt: str,
    *,
    model: str,
    workdir: str,
    timeout_sec: int,
    intent: str = "execution",
) -> tuple[Literal["success", "failed", "timeout"], str, str | None]:
    """Execute the prompt via the local ``claude`` CLI in headless mode.

    Runs with cwd=workdir and --add-dir=workdir so the agent can read/write the
    target surface repo, acceptEdits so file edits + git commits don't block on
    a human, and --output-format json so we can pull the final ``result`` text.
    Returns (status, text, error) matching the _run_opencode contract.

    intent="review" runs as a pure-text judgment: the diff and the analysis are
    already embedded in the prompt, so the review agent gets NO tools and is not
    pointed at the repo (no --add-dir). This stops the model from wandering off
    to "find the analysis file" in the worktree and refusing to judge — it must
    decide from the text it was given.
    """
    review_mode = intent == "review"
    if review_mode:
        # Pure-text verdict: deny all tools so the agent can't explore the repo.
        permission_mode = "default"
        allowed_tools = None
    else:
        # acceptEdits auto-approves file edits but NOT Bash; the execution prompt
        # asks the agent to `git add` + `git commit`, so explicitly allow git
        # (plus common read-only inspection commands) without opening up all Bash.
        permission_mode = "acceptEdits"
        allowed_tools = "Bash(git:*) Bash(ls:*) Bash(cat:*) Bash(grep:*) Bash(find:*)"

    # NOTE: the prompt is passed via stdin (UTF-8 bytes), NOT as a command-line
    # argument. On Windows the `claude.CMD` wrapper mangles non-ASCII argv (CJK
    # prompts arrive garbled — "Your message has some garbled characters"), so
    # we feed it on stdin and read stdout as bytes, decoding UTF-8 ourselves.
    cmd = [
        _claude_bin(),
        "-p",
        "--output-format", "json",
        "--permission-mode", permission_mode,
    ]
    if allowed_tools is not None:
        cmd.extend(["--allowedTools", allowed_tools])
    else:
        # Review: forbid every tool — judgment is from the prompt text alone.
        cmd.extend(["--disallowedTools", "Bash Edit Write Read Grep Glob WebFetch WebSearch Task"])
    if not review_mode:
        cmd.extend(["--add-dir", workdir])
    # Empty/"default" model → let the CLI pick its configured default.
    if model and model not in ("default", "glm-5.1"):
        cmd.extend(["--model", model])

    # Review runs in a NEUTRAL non-repo dir, not the worktree: when claude starts
    # inside the git repo being reviewed it tries to explore that repo and ignores
    # the diff embedded in the prompt. We use the OS temp root (a real, non-empty
    # directory that is NOT a git repo) so the agent answers from the prompt text.
    run_cwd = workdir
    if review_mode:
        import tempfile
        run_cwd = tempfile.gettempdir()

    try:
        proc = subprocess.run(
            cmd,
            input=prompt.encode("utf-8"),
            capture_output=True,
            cwd=run_cwd,
            env=_claude_env(),
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return "timeout", "", f"claude timed out after {timeout_sec}s"
    except FileNotFoundError:
        # claude 没装/不在 PATH —— 友好提示而非崩溃。
        return "failed", "", (
            "未找到 claude CLI。请先安装 Claude Code CLI 并登录，或用 CLAUDE_CLI_PATH "
            "指定路径；也可改用 ASP_AGENT_BACKEND=cursor。"
        )

    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")

    # Parse the single-result JSON envelope; fall back to raw stdout.
    result_text = ""
    is_error = proc.returncode != 0
    try:
        payload = json.loads(stdout.strip())
        if isinstance(payload, dict):
            result_text = (payload.get("result") or "").strip()
            is_error = bool(payload.get("is_error")) or is_error
    except (json.JSONDecodeError, ValueError):
        result_text = stdout.strip()

    if os.getenv("AGENT_CLIENT_DEBUG", "").lower() in ("1", "true") or proc.returncode != 0:
        _debug_path = _ASP_ROOT / "logs" / "agent_client_debug.log"
        try:
            _debug_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_debug_path, "a", encoding="utf-8") as _df:
                _df.write(f"\n{'='*60}\n[claude] prompt_len={len(prompt)} rc={proc.returncode}\n")
                _df.write(f"--- result_text ---\n{result_text}\n")
                _df.write(f"--- stderr (first 3000) ---\n{stderr[:3000]}\n")
        except OSError:
            pass

    if is_error and not result_text:
        return "failed", (stderr or stdout)[:4000], f"claude exited with code {proc.returncode}"

    return "success", result_text or stdout[:4000], None


# ---------------------------------------------------------------------------
# Cursor 后端（cursor-agent CLI）
# ---------------------------------------------------------------------------
# 这是给"团队成员用 Cursor 而非 Claude"准备的可选后端。默认仍是 claude（见 _BACKEND）；
# 想换成 Cursor 只需在 .env 里设 ASP_AGENT_BACKEND=cursor，无需改任何代码。
#
# ⚠️ 重大限制（来自 Cursor 官方文档 cursor.com/docs/cli/headless）：
#   cursor-agent 的无头模式 (-p) **要求一个真实 TTY**，在纯后台/脚本/子进程里
#   直接调用会**无限挂死**。我们的流水线是定时任务后台无人值守跑的，没有 TTY，
#   所以 cursor 后端在"集中式定时任务"场景下会卡死。
#   → 只有在「人坐在终端前手动跑一次」(run_*_once.bat / 手动命令) 时才适合用 cursor。
#   → 若要让 cursor 在后台定时任务里也能跑，需要用 tmux/conpty 之类包一个伪 TTY，
#     当前未实现（集中式部署请继续用默认的 claude 后端）。
# 参数对照（cursor-agent vs claude）：
#   应用文件改动: --force            (claude 是 --permission-mode acceptEdits)
#   输出 JSON:    --output-format json (与 claude 相同，结果同样在 .result 字段)
#   选模型:       --model            (与 claude 相同)
#   认证:         环境变量 CURSOR_API_KEY (claude 用登录态)
def _cursor_bin() -> str:
    """定位 cursor-agent CLI 路径。可用 CURSOR_CLI_PATH 覆盖。"""
    return (
        os.environ.get("CURSOR_CLI_PATH")
        or shutil.which("cursor-agent")
        or shutil.which("agent")
        or "cursor-agent"
    )


def _run_cursor(
    prompt: str,
    *,
    model: str,
    workdir: str,
    timeout_sec: int,
    intent: str = "execution",
) -> tuple[Literal["success", "failed", "timeout"], str, str | None]:
    """通过本机 ``cursor-agent`` CLI 无头执行 prompt。

    返回 (status, text, error)，契约与 _run_claude 一致，可直接被 _dispatch 复用。
    review intent 走纯文本判断：不加 --force（不改文件），在中性临时目录跑，避免
    agent 去探索仓库而无视 prompt 里已嵌入的 diff（与 claude 的 review 处理一致）。
    """
    review_mode = intent == "review"

    cmd = [
        _cursor_bin(),
        "-p",
        "--output-format", "json",
    ]
    # 非 review：允许直接改文件（写代码 + git commit 需要）。
    # review：不加 --force，纯读，只输出判断。
    if not review_mode:
        cmd.append("--force")
    # 空/"default"/"glm-5.1" → 让 CLI 用它配置的默认模型，不显式传 --model。
    if model and model not in ("default", "glm-5.1"):
        cmd.extend(["--model", model])

    # review 在中性非仓库目录跑（同 claude：避免 agent 跑去探索被审仓库）。
    run_cwd = workdir
    if review_mode:
        import tempfile
        run_cwd = tempfile.gettempdir()

    # 认证：cursor-agent 用 CURSOR_API_KEY 环境变量（或已登录态）。沿用当前环境即可。
    env = dict(os.environ)

    try:
        proc = subprocess.run(
            cmd,
            input=prompt.encode("utf-8"),
            capture_output=True,
            cwd=run_cwd,
            env=env,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        # 超时最常见的原因就是上面说的 TTY 挂死——给出明确提示便于排查。
        return "timeout", "", (
            f"cursor-agent timed out after {timeout_sec}s "
            f"(无头模式需真实 TTY；后台定时任务请改用 ASP_AGENT_BACKEND=claude)"
        )
    except FileNotFoundError:
        # cursor-agent 没装/不在 PATH —— 给出可操作的提示，而不是让流水线崩溃。
        return "failed", "", (
            "未找到 cursor-agent CLI。请先安装 Cursor CLI 并设置 CURSOR_API_KEY，"
            "或用 CURSOR_CLI_PATH 指定路径；也可改回 ASP_AGENT_BACKEND=claude。"
        )

    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")

    # 解析单结果 JSON 信封（与 claude 同结构：{"result": ..., "is_error": ...}）。
    result_text = ""
    is_error = proc.returncode != 0
    try:
        payload = json.loads(stdout.strip())
        if isinstance(payload, dict):
            result_text = (payload.get("result") or "").strip()
            is_error = bool(payload.get("is_error")) or is_error
    except (json.JSONDecodeError, ValueError):
        result_text = stdout.strip()

    if os.getenv("AGENT_CLIENT_DEBUG", "").lower() in ("1", "true") or proc.returncode != 0:
        _debug_path = _ASP_ROOT / "logs" / "agent_client_debug.log"
        try:
            _debug_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_debug_path, "a", encoding="utf-8") as _df:
                _df.write(f"\n{'='*60}\n[cursor] prompt_len={len(prompt)} rc={proc.returncode}\n")
                _df.write(f"--- result_text ---\n{result_text}\n")
                _df.write(f"--- stderr (first 3000) ---\n{stderr[:3000]}\n")
        except OSError:
            pass

    if is_error and not result_text:
        return "failed", (stderr or stdout)[:4000], f"cursor-agent exited with code {proc.returncode}"

    return "success", result_text or stdout[:4000], None


def _run_opencode(
    prompt: str,
    *,
    model: str,
    agent: str,
    workdir: str,
    timeout_sec: int,
) -> tuple[Literal["success", "failed", "timeout"], str, str | None]:
    """Execute via opencode_job.py subprocess. Returns (status, output, error)."""
    cmd = [
        sys.executable,
        str(_WORKSPACE_ROOT / "tools" / "opencode_job.py"),
        prompt,
        "--title", "ASP-Agent",
        "--model", model,
        "--agent", agent,
    ]
    if workdir:
        cmd.extend(["--workdir", workdir])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_WORKSPACE_ROOT),
            timeout=timeout_sec,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assistant_text = _extract_last_assistant_block(combined)

        # DEBUG: dump raw output for diagnosis (opt-in or on failure)
        _write_debug = os.getenv("AGENT_CLIENT_DEBUG", "").lower() in ("1", "true") or proc.returncode != 0
        if _write_debug:
            _debug_path = _ASP_ROOT / "logs" / "agent_client_debug.log"
            try:
                _debug_path.parent.mkdir(parents=True, exist_ok=True)
                with open(_debug_path, "a", encoding="utf-8") as _df:
                    _df.write(f"\n{'='*60}\n")
                    _df.write(f"prompt_len={len(prompt)}\n")
                    _df.write(f"returncode={proc.returncode}\n")
                    _df.write(f"assistant_text_len={len(assistant_text) if assistant_text else 0}\n")
                    _df.write(f"--- assistant_text ---\n{assistant_text}\n")
                    _df.write(f"--- combined (first 5000) ---\n{combined[:5000]}\n")
            except Exception:
                pass

        if proc.returncode != 0 and not assistant_text:
            return "failed", combined[:4000], f"opencode_job exited with code {proc.returncode}"

        return "success", assistant_text or combined[:4000], None

    except subprocess.TimeoutExpired:
        return "timeout", "", f"opencode timed out after {timeout_sec}s"


class AgentClient:
    """Send a prompt to the configured coding-agent backend and return the result."""

    def __init__(self, model: str = "default", agent: str = "OpenCode-Builder") -> None:
        self._model = model
        self._agent = agent

    def run(
        self,
        prompt: str,
        *,
        intent: str = "execution",
        workdir: str | Path | None = None,
        timeout_sec: int | None = None,
        executor: str | None = None,
        model: str | None = None,
        finalize_prompt: str | None = None,
        validate: Callable[[str], bool] | None = None,
    ) -> AgentRunResult:
        timeout = timeout_sec or int(os.getenv("AGENT_CLIENT_TIMEOUT", "3600"))
        workdir_str = str(workdir) if workdir else str(_ASP_ROOT)
        use_model = model or self._model
        backend = (executor or _BACKEND).strip().lower()

        def _dispatch(p: str, t: int) -> tuple[Literal["success", "failed", "timeout"], str, str | None]:
            if backend == "opencode":
                return _run_opencode(
                    p, model=use_model, agent=self._agent,
                    workdir=workdir_str, timeout_sec=t,
                )
            if backend == "cursor":
                # 团队成员用 Cursor 时的后端。注意：cursor 无头模式需真实 TTY，
                # 仅适合"人手动跑一次"，不适合后台定时任务（见 _run_cursor 注释）。
                return _run_cursor(
                    p, model=use_model, workdir=workdir_str, timeout_sec=t,
                    intent=intent,
                )
            return _run_claude(
                p, model=use_model, workdir=workdir_str, timeout_sec=t,
                intent=intent,
            )

        print(f"  Agent route: intent={intent} executor={backend} model={use_model}")

        t0 = time.time()
        status, text, error = _dispatch(prompt, timeout)
        elapsed = int(time.time() - t0)

        if status == "success" and text:
            if validate and not validate(text) and finalize_prompt:
                print(f"  Output validation failed, requesting finalize (with prior output)...")
                # Feed the first-round output back so model can reformat
                reformat_prompt = (
                    f"{finalize_prompt}\n\n"
                    f"## 你上一轮的分析结果（需要重新格式化为 8 章节）\n\n"
                    f"{text[:6000]}"
                )
                s2, t2, e2 = _dispatch(reformat_prompt, min(timeout, 600))
                if s2 == "success" and t2:
                    text = t2

            if validate and not validate(text):
                return AgentRunResult(
                    status="failed", text=text, executor=backend,
                    model=use_model, intent=intent, elapsed_sec=elapsed,
                    error="output failed validation",
                )

            return AgentRunResult(
                status="success", text=text, executor=backend,
                model=use_model, intent=intent, elapsed_sec=elapsed,
            )

        return AgentRunResult(
            status=status, text=text, executor=backend,
            model=use_model, intent=intent, elapsed_sec=elapsed,
            error=error or "empty output",
        )
