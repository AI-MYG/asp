"""OpenCode Server HTTP REST client for ASP automation scripts.

Connects to a local OpenCode Server instance for agent tasks
(triage, analysis, observer, reflector).

Requires: pip install requests
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

import requests

# Load .env from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
_env_file = REPO_ROOT / ".env"
if _env_file.is_file():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        if _k not in os.environ:
            os.environ[_k] = _v.strip()

MESSAGE_TIMEOUT = int(os.getenv("OPENCODE_MESSAGE_TIMEOUT", "3600"))


class OpenCodeClient:
    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.base_url = base_url or os.getenv("OPENCODE_BASE_URL", "http://localhost:4096")
        self.username = username or os.getenv("OPENCODE_USERNAME", "opencode")
        self.password = password or os.getenv("OPENCODE_PASSWORD", "")

        if not self.password:
            raise ValueError(
                "OPENCODE_PASSWORD not set. Configure in .env or pass explicitly."
            )

        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.headers = {"Authorization": f"Basic {encoded}"}

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", headers=self.headers, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def create_session(self, title: str) -> str | None:
        try:
            resp = requests.post(
                f"{self.base_url}/session",
                json={"title": title},
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["id"]
        except Exception as e:
            print(f"Error creating session: {e}")
            return None

    def send_message(
        self,
        session_id: str,
        message: str,
        model_id: str = "claude-sonnet-4-20250514",
        provider_id: str | None = None,
    ) -> dict[str, Any] | None:
        if provider_id is None:
            if model_id.startswith("glm-"):
                provider_id = "zai-coding-plan"
            elif "claude" in model_id or "anthropic" in model_id:
                provider_id = "anthropic"
            else:
                provider_id = "google"

        payload = {
            "parts": [{"type": "text", "text": message}],
            "model": {"modelID": model_id, "providerID": provider_id},
        }

        try:
            resp = requests.post(
                f"{self.base_url}/session/{session_id}/message",
                json=payload,
                headers=self.headers,
                timeout=MESSAGE_TIMEOUT,
            )
            resp.raise_for_status()
            if not resp.text.strip():
                return None
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return None

    def get_session_messages(self, session_id: str) -> list[dict] | None:
        try:
            resp = requests.get(
                f"{self.base_url}/session/{session_id}/message",
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error getting messages: {e}")
            return None

    def delete_session(self, session_id: str) -> bool:
        try:
            resp = requests.delete(
                f"{self.base_url}/session/{session_id}",
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def wait_for_session_complete(
        self, session_id: str, poll_interval: int = 15, max_wait: int = 7200
    ) -> bool:
        start = time.time()
        while (time.time() - start) < max_wait:
            try:
                resp = requests.get(
                    f"{self.base_url}/session/{session_id}",
                    headers=self.headers,
                    timeout=10,
                )
                resp.raise_for_status()
                info = resp.json()
                running = info.get("running") or info.get("busy")
                status = info.get("status", "")
                if not running and status not in ("running", "busy"):
                    return True
            except Exception:
                pass
            time.sleep(poll_interval)
        return False
