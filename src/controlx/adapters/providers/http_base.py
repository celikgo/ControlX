"""Shared HTTP plumbing for BYOK provider adapters."""

from __future__ import annotations

import httpx

from ...core.models import Pack, Patch
from ...core.ports import (
    ApplyResult,
    Capabilities,
    Completion,
    CompletionRequest,
    Health,
    RemoteRef,
)
from ...errors import AuthError, CapabilityError, ProviderError

TIMEOUT = httpx.Timeout(60.0, connect=15.0)


class HttpProviderAdapter:
    """Base class. Subclasses define the wire format only."""

    id = "http"
    base_url = ""
    default_model = ""
    #: Consumer subscriptions (ChatGPT Plus, Claude Pro, X Premium) are not API
    #: credentials. None of these vendors publishes a project-write API for
    #: third-party apps, so writes fall back to an inject bundle. See docs/PROVIDERS.md.
    caps = Capabilities(
        can_complete=True,
        can_list_projects=False,
        can_write_instructions=False,
        can_upload_files=False,
        can_oauth=False,
        requires_inject=True,
        note="completion API only; project writes fall back to an inject bundle",
    )

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or self.default_model
        self.base_url = (base_url or self.base_url).rstrip("/")
        self._client = client

    # ------------------------------------------------------------ plumbing --
    def _require_key(self) -> str:
        if not self.api_key:
            raise AuthError(
                f"no API key for {self.id}",
                hint=f"controlx auth add --provider {self.id} --mode api_key",
            )
        return self.api_key

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._require_key()}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict) -> dict:
        client = self._client or httpx.AsyncClient(timeout=TIMEOUT)
        try:
            response = await client.post(
                f"{self.base_url}{path}", json=payload, headers=self.headers()
            )
            if response.status_code in (401, 403):
                raise AuthError(f"{self.id}: credentials rejected ({response.status_code})")
            if response.status_code >= 400:
                raise ProviderError(f"{self.id}: HTTP {response.status_code} {response.text[:300]}")
            return dict(response.json())
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.id}: transport error: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()

    # --------------------------------------------------------- port surface --
    async def health(self) -> Health:
        try:
            completion = await self.complete(
                CompletionRequest(prompt="Reply with the single word: ok", max_tokens=8)
            )
        except (AuthError, ProviderError) as exc:
            return Health(ok=False, detail=str(exc))
        return Health(ok=bool(completion.text.strip()), detail=f"model={completion.model}")

    async def complete(self, req: CompletionRequest) -> Completion:  # pragma: no cover - abstract
        raise NotImplementedError

    async def list_remote_projects(self) -> list[RemoteRef]:
        return []

    async def pull_project(self, ref: str) -> Pack:
        raise CapabilityError(
            f"{self.id} exposes no project-read API",
            hint="export the project from the web UI and run `controlx pack import`",
        )

    async def apply_patch(self, ref: str | None, patch: Patch) -> ApplyResult:
        return ApplyResult(
            applied=False,
            detail=(
                f"{self.id} has no public project-write API; ControlX did not change anything "
                "remotely. Use the inject bundle."
            ),
        )

    async def capabilities(self) -> Capabilities:
        return self.caps
