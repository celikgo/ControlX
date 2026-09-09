"""Application context: wires config, vault, index and secrets to the ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .adapters.db import Index
from .adapters.judge import LLMJudge
from .adapters.providers.inject import InjectAdapter
from .adapters.providers.local import LocalPackAdapter
from .adapters.providers.registry import build_adapter, canonical_provider
from .adapters.secrets import SecretStore
from .adapters.vault import PackStore
from .config import Config, load_config
from .core.audit import HeuristicJudge
from .core.models import Pack, Workspace
from .core.ports import Judge, ProviderAdapter
from .errors import NotFoundError, UserError


@dataclass(slots=True)
class Target:
    """A resolved audit/apply target."""

    ref: str
    adapter: ProviderAdapter
    pack: Pack | None = None
    workspace: Workspace | None = None

    @property
    def is_local(self) -> bool:
        return self.pack is not None


class AppContext:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        cfg.ensure_dirs()
        self.store = PackStore(cfg.packs_dir)
        self.index = Index(cfg.db_path, cfg.audits_dir, cfg.patches_dir)
        self.secrets = SecretStore(cfg.home)

    @classmethod
    def load(cls, home: Path | None = None) -> AppContext:
        return cls(load_config(home))

    def close(self) -> None:
        self.index.close()

    # ------------------------------------------------------------- targets --
    def resolve_target(self, ref: str) -> Target:
        ref = ref.strip()
        if not ref:
            raise UserError("empty target reference")

        if ref.startswith("pack:"):
            slug = ref.split(":", 1)[1]
            pack = self.store.load(slug)
            return Target(ref=f"pack:{slug}", adapter=LocalPackAdapter(pack, self.store), pack=pack)

        workspace = self.index.find_workspace(ref)
        if workspace is None and ":" not in ref and self.store.exists(ref):
            pack = self.store.load(ref)
            return Target(ref=f"pack:{ref}", adapter=LocalPackAdapter(pack, self.store), pack=pack)

        if workspace is None:
            provider_name, _, account = ref.partition(":")
            provider = canonical_provider(provider_name)
            if provider not in {"openai", "anthropic", "xai"}:
                raise NotFoundError(
                    f"cannot resolve target '{ref}'",
                    hint="use pack:<slug>, a workspace name, or <provider>:<account>",
                )
            workspace = Workspace(
                name=ref, provider=provider, account=account or "default", auth_mode="api_key"
            )

        return Target(ref=workspace.ref, adapter=self.adapter_for(workspace), workspace=workspace)

    def adapter_for(self, workspace: Workspace) -> ProviderAdapter:
        if workspace.auth_mode == "session" or workspace.provider == "mcp":
            return InjectAdapter(workspace.name)
        return build_adapter(
            workspace.provider,
            api_key=self.secrets.get(workspace.provider, workspace.account),
            model=workspace.model or self.cfg.model_for(workspace.provider),
        )

    # --------------------------------------------------------------- judge --
    def judge(self) -> Judge:
        if self.cfg.judge_mode != "llm" or not self.cfg.judge_provider:
            return HeuristicJudge()
        provider = canonical_provider(self.cfg.judge_provider)
        adapter = build_adapter(
            provider,
            api_key=self.secrets.get(provider),
            model=self.cfg.judge_model or self.cfg.model_for(provider),
        )
        return LLMJudge(adapter, self.cfg.judge_model or None)
