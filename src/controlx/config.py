"""Local-first configuration. Everything lives under $CONTROLX_HOME (~/.controlx)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-5",
    "xai": "grok-4",
}

CONFIG_TEMPLATE = """# ControlX configuration
# Docs: docs/VAULT.md

[core]
vault_dir = "{vault}"
db_path = "{db}"
logs_dir = "{logs}"
min_score = 70.0

[judge]
# "heuristic" is deterministic and offline. Set provider/model to use an LLM judge.
mode = "heuristic"
provider = ""
model = ""

[models]
openai = "{openai}"
anthropic = "{anthropic}"
xai = "{xai}"

[mcp]
host = "127.0.0.1"
port = 8765
"""


def home_dir() -> Path:
    return Path(os.environ.get("CONTROLX_HOME", Path.home() / ".controlx")).expanduser()


@dataclass(slots=True)
class Config:
    home: Path
    vault_dir: Path
    db_path: Path
    logs_dir: Path
    min_score: float = 70.0
    judge_mode: str = "heuristic"
    judge_provider: str = ""
    judge_model: str = ""
    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    @property
    def packs_dir(self) -> Path:
        return self.vault_dir / "packs"

    @property
    def audits_dir(self) -> Path:
        return self.vault_dir / "audits"

    @property
    def patches_dir(self) -> Path:
        return self.vault_dir / "patches"

    @property
    def exports_dir(self) -> Path:
        return self.home / "exports"

    def model_for(self, provider: str) -> str:
        return self.models.get(provider) or DEFAULT_MODELS.get(provider, "")

    def ensure_dirs(self) -> None:
        for path in (
            self.home,
            self.vault_dir,
            self.packs_dir,
            self.audits_dir,
            self.patches_dir,
            self.logs_dir,
            self.exports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def default_config(home: Path | None = None) -> Config:
    root = home or home_dir()
    return Config(
        home=root,
        vault_dir=root / "vault",
        db_path=root / "controlx.db",
        logs_dir=root / "logs",
    )


def load_config(home: Path | None = None) -> Config:
    cfg = default_config(home)
    path = cfg.config_path
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    core = data.get("core", {})
    cfg.vault_dir = Path(core.get("vault_dir", cfg.vault_dir)).expanduser()
    cfg.db_path = Path(core.get("db_path", cfg.db_path)).expanduser()
    cfg.logs_dir = Path(core.get("logs_dir", cfg.logs_dir)).expanduser()
    cfg.min_score = float(core.get("min_score", cfg.min_score))
    judge = data.get("judge", {})
    cfg.judge_mode = judge.get("mode", cfg.judge_mode)
    cfg.judge_provider = judge.get("provider", "")
    cfg.judge_model = judge.get("model", "")
    cfg.models = {**DEFAULT_MODELS, **data.get("models", {})}
    mcp = data.get("mcp", {})
    cfg.mcp_host = mcp.get("host", cfg.mcp_host)
    cfg.mcp_port = int(mcp.get("port", cfg.mcp_port))
    return cfg


def write_config(cfg: Config) -> Path:
    cfg.home.mkdir(parents=True, exist_ok=True)
    cfg.config_path.write_text(
        CONFIG_TEMPLATE.format(
            vault=cfg.vault_dir,
            db=cfg.db_path,
            logs=cfg.logs_dir,
            openai=cfg.model_for("openai"),
            anthropic=cfg.model_for("anthropic"),
            xai=cfg.model_for("xai"),
        ),
        encoding="utf-8",
    )
    return cfg.config_path
