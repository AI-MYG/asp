"""ASP AgentClient facade — delegates to rootgrove multi-executor routing.

Routing SSOT: ``$WORKSPACE_ROOT/tools/agent_clients/config.yaml``
(C/D prefer Cursor; review prefers Claude Code; OpenCode stays in fallback chains).

Usage:
    from tools.agent_client import AgentClient
    result = AgentClient().run(prompt, intent="analysis", workdir="/path/to/workdir")
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

_ASP_ROOT = Path(__file__).resolve().parent.parent
_WORKSPACE_ROOT = Path(
    os.environ.get("WORKSPACE_ROOT")
    or os.environ.get("ASP_WORKTREE_ROOT")
    or str(_ASP_ROOT.parent.parent)
)

_DelegateCls: type[Any] | None = None
_AgentRunResult: type[Any] | None = None


def _ensure_rootgrove_delegate() -> type[Any]:
    """Import rootgrove ``tools.agent_clients.client.AgentClient`` despite asp-infra ``tools`` package."""
    global _DelegateCls, _AgentRunResult
    if _DelegateCls is not None:
        return _DelegateCls

    root = str(_WORKSPACE_ROOT.resolve())
    self_mod = sys.modules.get("tools.agent_client")

    for key in list(sys.modules):
        if key == "tools" or (key.startswith("tools.") and key != "tools.agent_client"):
            del sys.modules[key]

    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)

    from tools.agent_clients.client import AgentClient as cls
    from tools.agent_clients.client import AgentRunResult as run_result_cls

    _DelegateCls = cls
    _AgentRunResult = run_result_cls

    # Keep this facade importable as tools.agent_client for ASP import_chain.
    if self_mod is not None:
        sys.modules["tools.agent_client"] = self_mod

    return cls


# Lazily compatible re-export for callers that type-check AgentRunResult.
def __getattr__(name: str) -> Any:
    if name == "AgentRunResult":
        _ensure_rootgrove_delegate()
        assert _AgentRunResult is not None
        return _AgentRunResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class AgentClient:
    """Same run() contract as before; routing comes from rootgrove AgentClient."""

    def __init__(self, model: str | None = None, agent: str | None = None) -> None:
        # Legacy ctor args kept for call-site compatibility; intent routing owns model choice.
        self._model = model
        self._agent = agent  # unused; OpenCode agent name was ASP-only
        self._inner = _ensure_rootgrove_delegate()()

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
    ) -> Any:
        return self._inner.run(
            prompt,
            intent=intent,
            workdir=workdir if workdir is not None else _ASP_ROOT,
            timeout_sec=timeout_sec,
            executor=executor,
            model=model or self._model,
            finalize_prompt=finalize_prompt,
            validate=validate,
        )
