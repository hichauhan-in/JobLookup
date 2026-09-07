"""Talk to Copilot through the JobLookup Bridge VS Code extension.

This is the sanctioned way to use a Copilot seat from your own code: the
extension calls VS Code's Language Model API (``vscode.lm``), which is the same
API every Copilot-powered extension uses. Nothing here impersonates a Copilot
client or touches a private endpoint.

The extension writes a handshake file containing the port and a per-session
bearer token. Requiring that token means another process on the machine cannot
quietly spend your Copilot quota.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from joblookup.config import VSCodeLLMConfig
from joblookup.llm.base import (
    ChatMessage,
    LLMError,
    LLMUnavailableError,
    ProviderStatus,
)
from joblookup.paths import user_state_dir

SETUP_HINT = (
    "Run .\\scripts\\install-bridge.ps1, reload VS Code, then run 'JobLookup Bridge: "
    "Authorise Copilot Access' from the command palette. A VS Code window signed in "
    "to GitHub Copilot must stay open while JobLookup is scoring."
)

EXTENSION_ID = "joblookup.joblookup-bridge"
HANDSHAKE_NAME = "bridge.json"

#: Where the extension listens unless the user moved it. Only used to tell
#: "never started" apart from "started, but we cannot see its handshake".
DEFAULT_PORT = 8771


def _something_is_listening(port: int = DEFAULT_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.15)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def extension_state(handshake_file: str | None = None) -> dict[str, object]:
    """Where the bridge has got to, so the UI can give the right instruction.

    "Not installed", "installed but VS Code has not loaded it" and "was running,
    now gone" need three different fixes, and guessing between them wastes the
    user's time.
    """
    installed: list[str] = []
    for root in (".vscode", ".vscode-insiders", ".vscode-server"):
        extensions = Path.home() / root / "extensions"
        if not extensions.is_dir():
            continue
        installed += [
            entry.name.rsplit("-", 1)[-1]
            for entry in extensions.iterdir()
            if entry.is_dir() and entry.name.startswith(EXTENSION_ID)
        ]

    path = (
        Path(handshake_file).expanduser() if handshake_file else user_state_dir() / HANDSHAKE_NAME
    )
    return {
        "extension_installed": bool(installed),
        "extension_version": installed[0] if installed else "",
        "handshake_present": path.is_file() or bool(list((path.parent / "bridges").glob("*.json"))),
        "handshake_path": str(path),
    }


class VSCodeBridgeProvider:
    key = "vscode"
    label = "GitHub Copilot (via VS Code bridge)"

    def __init__(self, config: VSCodeLLMConfig) -> None:
        self.config = config
        self._health_payload: dict[str, Any] | None = None

    # --- handshake ---------------------------------------------------------
    def _handshake_path(self) -> Path:
        if self.config.handshake_file:
            return Path(self.config.handshake_file).expanduser()
        return user_state_dir() / HANDSHAKE_NAME

    @staticmethod
    def _validated_endpoint(base_url: str, token: str) -> tuple[str, str]:
        try:
            address = urlsplit(base_url)
            valid = (
                address.scheme == "http"
                and address.hostname in {"127.0.0.1", "localhost", "::1"}
                and address.port is not None
                and address.port > 0
                and not (address.username or address.password or address.query or address.fragment)
                and address.path in {"", "/"}
                and len(token) >= 16
            )
        except ValueError:
            valid = False
        if not valid:
            raise LLMUnavailableError(
                "The bridge discovery file has an invalid local endpoint or token."
            )
        return base_url.rstrip("/"), token

    def _endpoint(self) -> tuple[str, str]:
        self._health_payload = None
        if self.config.base_url:
            return self._validated_endpoint(self.config.base_url, self.config.token or "")
        legacy = self._handshake_path()
        candidates = [legacy]
        if not self.config.handshake_file:
            discovered = list((legacy.parent / "bridges").glob("*.json"))
            candidates = (
                sorted(discovered, key=lambda path: path.name, reverse=True)[:16] + candidates
            )
        fallback = None
        for path in candidates:
            try:
                if path.stat().st_size > 8192:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                base, token = self._validated_endpoint(
                    str(data.get("base_url") or ""), str(data.get("token") or "")
                )
                response = httpx.get(
                    f"{base}/health", headers=self._headers(token), timeout=0.8, trust_env=False
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not payload.get("ok"):
                    continue
                if payload.get("copilot_available") and payload.get("consented"):
                    self._health_payload = payload
                    return base, token
                if fallback is None:
                    fallback = (base, token, payload)
            except (OSError, ValueError, httpx.HTTPError, LLMUnavailableError):
                continue
        if fallback:
            base, token, self._health_payload = fallback
            return base, token
        raise LLMUnavailableError(
            "No reachable VS Code bridge was found. Run 'JobLookup Bridge: Restart Server' "
            "in an open VS Code window, then authorize Copilot access. Local matching still works."
        )

    def _headers(self, token: str) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        return headers

    # --- provider interface ------------------------------------------------
    def status(self) -> ProviderStatus:
        try:
            base_url, token = self._endpoint()
        except LLMUnavailableError as exc:
            return ProviderStatus(self.key, self.label, False, str(exc), setup_hint=SETUP_HINT)

        try:
            if self._health_payload is not None:
                payload = self._health_payload
            else:
                response = httpx.get(
                    f"{base_url}/health", headers=self._headers(token), timeout=3.0, trust_env=False
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            return ProviderStatus(
                self.key,
                self.label,
                False,
                f"Bridge did not respond at {base_url}: {exc}",
                setup_hint=SETUP_HINT,
            )

        models = [str(model) for model in payload.get("models") or []]
        active = self.config.model or str(payload.get("default_model") or "")
        if not payload.get("copilot_available", True):
            return ProviderStatus(
                self.key,
                self.label,
                False,
                "The bridge is running but VS Code reports no Copilot models. Sign in "
                "to GitHub Copilot in VS Code and try again.",
                models=models,
                setup_hint=SETUP_HINT,
            )
        if not payload.get("consented", True):
            return ProviderStatus(
                self.key,
                self.label,
                False,
                "Waiting for consent. Run 'JobLookup Bridge: Authorise Copilot Access' "
                "from the VS Code command palette once.",
                models=models,
                setup_hint=SETUP_HINT,
            )
        return ProviderStatus(
            self.key,
            self.label,
            True,
            f"Connected to VS Code at {base_url}",
            models=models,
            active_model=active,
        )

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        expect_json: bool = False,
    ) -> str:
        base_url, token = self._endpoint()
        body: dict[str, Any] = {
            "messages": [message.to_dict() for message in messages],
            "temperature": temperature,
        }
        if self.config.model:
            body["model"] = self.config.model
        if self.config.reasoning_effort:
            body["reasoning_effort"] = self.config.reasoning_effort
        if self.config.context_window_tokens:
            body["context_window_tokens"] = self.config.context_window_tokens
        if max_tokens:
            body["max_tokens"] = max_tokens

        try:
            response = httpx.post(
                f"{base_url}/v1/chat/completions",
                headers=self._headers(token),
                json=body,
                timeout=httpx.Timeout(15.0, read=self.config.request_timeout_s),
                trust_env=False,
            )
        except httpx.RequestError as exc:
            raise LLMUnavailableError(
                f"Lost contact with the VS Code bridge: {exc}. Is the VS Code window still open?"
            ) from exc

        if response.status_code in (401, 403):
            raise LLMUnavailableError(
                "Bridge access was denied. Restart the bridge and run 'JobLookup Bridge: "
                "Authorise Copilot Access' in VS Code. Your local matches are unaffected."
            )
        if response.status_code >= 400:
            raise LLMError(f"Bridge error {response.status_code}: {response.text[:400]}")

        payload = response.json()
        if payload.get("error"):
            raise LLMError(str(payload["error"]))
        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
        if not content:
            raise LLMError("The bridge returned an empty response.")
        return str(content)
