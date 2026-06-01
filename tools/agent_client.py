"""Simplified AgentClient for ASP — OpenCode executor only.

Merged from rootgrove's multi-executor AgentClient + OpenCodeExecutor into a
single self-contained module. ASP uses OpenCode as its sole coding agent.

Usage:
    from tools.agent_client import AgentClient
    result = AgentClient().run(prompt, intent="analysis", workdir="/path/to/workdir")
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

_ASP_ROOT = Path(__file__).resolve().parent.parent
_WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", str(_ASP_ROOT.parent.parent)))



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
            cwd=str(_WORKSPACE_ROOT),
            timeout=timeout_sec,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assistant_text = _extract_last_assistant_block(combined)

        # DEBUG: dump raw output for diagnosis
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
    """Send a prompt to OpenCode and return the result."""

    def __init__(self, model: str = "glm-5.1", agent: str = "OpenCode-Builder") -> None:
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

        print(f"  Agent route: intent={intent} executor=opencode model={use_model}")

        t0 = time.time()
        status, text, error = _run_opencode(
            prompt,
            model=use_model,
            agent=self._agent,
            workdir=workdir_str,
            timeout_sec=timeout,
        )
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
                s2, t2, e2 = _run_opencode(
                    reformat_prompt,
                    model=use_model,
                    agent=self._agent,
                    workdir=workdir_str,
                    timeout_sec=min(timeout, 600),
                )
                if s2 == "success" and t2:
                    text = t2

            if validate and not validate(text):
                return AgentRunResult(
                    status="failed", text=text, executor="opencode",
                    model=use_model, intent=intent, elapsed_sec=elapsed,
                    error="output failed validation",
                )

            return AgentRunResult(
                status="success", text=text, executor="opencode",
                model=use_model, intent=intent, elapsed_sec=elapsed,
            )

        return AgentRunResult(
            status=status, text=text, executor="opencode",
            model=use_model, intent=intent, elapsed_sec=elapsed,
            error=error or "empty output",
        )
