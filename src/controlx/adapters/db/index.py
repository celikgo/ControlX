"""SQLite operational index.

The vault is the source of truth; this database only makes registry lookups and
audit history fast. Deleting it is never data loss - `controlx doctor --reindex`
rebuilds it from the vault.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ...core.models import Audit, Bridge, Patch, Workspace

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    auth_mode TEXT NOT NULL,
    endpoint_kind TEXT NOT NULL,
    account TEXT NOT NULL DEFAULT 'default',
    remote_ref TEXT,
    model TEXT,
    last_seen_at TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS bridges (
    id TEXT PRIMARY KEY,
    source_pack_id TEXT NOT NULL,
    target_workspace_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    last_audit_id TEXT
);
CREATE TABLE IF NOT EXISTS audits (
    id TEXT PRIMARY KEY,
    bridge_id TEXT,
    source_slug TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    score_pct REAL NOT NULL,
    created_at TEXT NOT NULL,
    patch_id TEXT,
    path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patches (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    op_count INTEGER NOT NULL,
    path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audits_by_source ON audits(source_slug, created_at DESC);
"""


class Index:
    def __init__(self, db_path: Path, audits_dir: Path, patches_dir: Path) -> None:
        self.db_path = Path(db_path)
        self.audits_dir = Path(audits_dir)
        self.patches_dir = Path(patches_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audits_dir.mkdir(parents=True, exist_ok=True)
        self.patches_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ----------------------------------------------------------- workspaces --
    def upsert_workspace(self, ws: Workspace) -> None:
        self._conn.execute(
            """INSERT INTO workspaces
               (id,name,provider,auth_mode,endpoint_kind,account,remote_ref,model,last_seen_at,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, provider=excluded.provider, auth_mode=excluded.auth_mode,
                 endpoint_kind=excluded.endpoint_kind, account=excluded.account,
                 remote_ref=excluded.remote_ref, model=excluded.model,
                 last_seen_at=excluded.last_seen_at, notes=excluded.notes""",
            (
                ws.id,
                ws.name,
                ws.provider,
                ws.auth_mode,
                ws.endpoint_kind,
                ws.account,
                ws.remote_ref,
                ws.model,
                ws.last_seen_at.isoformat() if ws.last_seen_at else None,
                ws.notes,
            ),
        )
        self._conn.commit()

    def list_workspaces(self) -> list[Workspace]:
        rows = self._conn.execute("SELECT * FROM workspaces ORDER BY provider, name").fetchall()
        return [self._workspace(row) for row in rows]

    def find_workspace(self, needle: str) -> Workspace | None:
        for ws in self.list_workspaces():
            if needle in (ws.id, ws.name, ws.ref) or needle == f"{ws.provider}:{ws.name}":
                return ws
        return None

    def delete_workspace(self, ws_id: str) -> None:
        self._conn.execute("DELETE FROM workspaces WHERE id=?", (ws_id,))
        self._conn.commit()

    @staticmethod
    def _workspace(row: sqlite3.Row) -> Workspace:
        return Workspace(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            auth_mode=row["auth_mode"],
            endpoint_kind=row["endpoint_kind"],
            account=row["account"],
            remote_ref=row["remote_ref"],
            model=row["model"],
            last_seen_at=datetime.fromisoformat(row["last_seen_at"])
            if row["last_seen_at"]
            else None,
            notes=row["notes"],
        )

    # -------------------------------------------------------------- bridges --
    def upsert_bridge(self, bridge: Bridge) -> None:
        self._conn.execute(
            """INSERT INTO bridges (id,source_pack_id,target_workspace_id,direction,last_audit_id)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET last_audit_id=excluded.last_audit_id,
                 direction=excluded.direction""",
            (
                bridge.id,
                bridge.source_pack_id,
                bridge.target_workspace_id,
                bridge.direction,
                bridge.last_audit_id,
            ),
        )
        self._conn.commit()

    def list_bridges(self) -> list[Bridge]:
        rows = self._conn.execute("SELECT * FROM bridges").fetchall()
        return [
            Bridge(
                id=row["id"],
                source_pack_id=row["source_pack_id"],
                target_workspace_id=row["target_workspace_id"],
                direction=row["direction"],
                last_audit_id=row["last_audit_id"],
            )
            for row in rows
        ]

    def find_bridge(self, source_pack_id: str, target_ref: str) -> Bridge | None:
        row = self._conn.execute(
            "SELECT * FROM bridges WHERE source_pack_id=? AND target_workspace_id=?",
            (source_pack_id, target_ref),
        ).fetchone()
        if row is None:
            return None
        return Bridge(
            id=row["id"],
            source_pack_id=row["source_pack_id"],
            target_workspace_id=row["target_workspace_id"],
            direction=row["direction"],
            last_audit_id=row["last_audit_id"],
        )

    # --------------------------------------------------------------- audits --
    def save_audit(self, audit: Audit) -> Path:
        path = self.audits_dir / f"{audit.id}.json"
        path.write_text(audit.model_dump_json(indent=2), encoding="utf-8")
        self._conn.execute(
            """INSERT INTO audits
                 (id,bridge_id,source_slug,target_ref,score_pct,created_at,patch_id,path)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET score_pct=excluded.score_pct,
                 patch_id=excluded.patch_id, path=excluded.path""",
            (
                audit.id,
                audit.bridge_id,
                audit.source_slug,
                audit.target_ref,
                audit.score_pct,
                audit.created_at.isoformat(),
                audit.patch_id,
                str(path),
            ),
        )
        self._conn.commit()
        return path

    def load_audit(self, audit_id: str) -> Audit:
        row = self._conn.execute("SELECT path FROM audits WHERE id=?", (audit_id,)).fetchone()
        path = Path(row["path"]) if row else self.audits_dir / f"{audit_id}.json"
        return Audit.model_validate_json(path.read_text("utf-8"))

    def list_audits(self, source_slug: str | None = None, limit: int = 25) -> list[sqlite3.Row]:
        if source_slug:
            return self._conn.execute(
                "SELECT * FROM audits WHERE source_slug=? ORDER BY created_at DESC LIMIT ?",
                (source_slug, limit),
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM audits ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def latest_audit_id(self, source_slug: str | None = None) -> str | None:
        rows = self.list_audits(source_slug, limit=1)
        return rows[0]["id"] if rows else None

    def audit_id_for_patch(self, patch_id: str) -> str | None:
        row = self._conn.execute("SELECT audit_id FROM patches WHERE id=?", (patch_id,)).fetchone()
        return row["audit_id"] if row else None

    # -------------------------------------------------------------- patches --
    def save_patch(self, patch: Patch) -> Path:
        path = self.patches_dir / f"{patch.id}.json"
        path.write_text(patch.model_dump_json(indent=2), encoding="utf-8")
        self._conn.execute(
            """INSERT INTO patches (id,audit_id,target_ref,status,op_count,path)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status, op_count=excluded.op_count,
                 path=excluded.path""",
            (
                patch.id,
                patch.audit_id,
                patch.target_ref,
                patch.status.value,
                len(patch.ops),
                str(path),
            ),
        )
        self._conn.commit()
        return path

    def load_patch(self, patch_id: str) -> Patch:
        row = self._conn.execute("SELECT path FROM patches WHERE id=?", (patch_id,)).fetchone()
        path = Path(row["path"]) if row else self.patches_dir / f"{patch_id}.json"
        return Patch.model_validate_json(path.read_text("utf-8"))

    def patch_for_audit(self, audit_id: str) -> Patch | None:
        row = self._conn.execute(
            "SELECT id FROM patches WHERE audit_id=? ORDER BY rowid DESC LIMIT 1", (audit_id,)
        ).fetchone()
        return self.load_patch(row["id"]) if row else None

    def stats(self) -> dict[str, int]:
        def count(table: str) -> int:
            return int(self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])

        return {t: count(t) for t in ("workspaces", "bridges", "audits", "patches")}

    def dump_json(self) -> str:
        return json.dumps(self.stats(), indent=2)
