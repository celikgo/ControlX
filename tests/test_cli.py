"""CLI parity: the same use cases, scriptable, with contractual exit codes."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from controlx.cli import app
from controlx.services import EXAMPLES_DIR

runner = CliRunner()


def run(home: Path, *args: str):
    return runner.invoke(app, ["--home", str(home), *args])


def test_init_creates_the_home(tmp_path: Path):
    result = run(tmp_path / "h", "init")
    assert result.exit_code == 0
    assert (tmp_path / "h" / "config.toml").exists()
    assert (tmp_path / "h" / "vault" / "packs").is_dir()


def test_doctor_reports_json(home: Path):
    result = run(home, "doctor", "--json")
    assert result.exit_code == 0
    assert '"name"' in result.output


def test_pack_lifecycle(home: Path):
    assert run(home, "pack", "import", str(EXAMPLES_DIR / "demo-service")).exit_code == 0
    listing = run(home, "pack", "ls")
    assert "demo-service" in listing.output
    assert run(home, "probe", "ls", "demo-service").exit_code == 0
    passport = run(home, "pack", "passport", "demo-service")
    assert "ControlX Passport" in passport.output
    assert "Resume prompt" in passport.output


def test_audit_and_patch_flow_with_min_score(home: Path):
    run(home, "pack", "import", str(EXAMPLES_DIR / "demo-service"))
    run(home, "pack", "import", str(EXAMPLES_DIR / "demo-thin"))

    failing = run(
        home,
        "audit",
        "run",
        "--source",
        "demo-service",
        "--target",
        "pack:demo-thin",
        "--min-score",
        "70",
    )
    assert failing.exit_code == 3  # exit 3 = below threshold, for CI gates
    assert "41.7%" in failing.output

    assert run(home, "patch", "preview", "latest").exit_code == 0

    # applying without approval is refused
    assert run(home, "patch", "apply", "latest").exit_code == 1

    assert run(home, "patch", "apply", "latest", "--approve").exit_code == 0
    passing = run(
        home,
        "audit",
        "run",
        "--source",
        "demo-service",
        "--target",
        "pack:demo-thin",
        "--min-score",
        "70",
    )
    assert passing.exit_code == 0
    assert "83.3%" in passing.output


def test_unknown_pack_exits_one(home: Path):
    result = run(home, "pack", "show", "nope")
    assert result.exit_code == 1
    assert "not found" in result.output


def test_workspace_and_auth_listing(home: Path):
    added = run(home, "workspace", "add", "--provider", "anthropic", "--name", "Claude / Nakitte")
    assert added.exit_code == 0
    assert "anthropic:default" in added.output
    assert "Claude / Nakitte" in run(home, "workspace", "list").output
    assert run(home, "auth", "list").exit_code == 0


def test_oauth_mode_is_honest_about_being_unavailable(home: Path):
    result = run(home, "auth", "add", "--provider", "openai", "--mode", "oauth")
    assert result.exit_code == 1
    assert "LIMITED" in result.output
    assert "will not scrape" in result.output


def test_export_formats(home: Path, tmp_path: Path):
    run(home, "pack", "import", str(EXAMPLES_DIR / "demo-service"))
    for fmt in ("dir", "md", "passport", "inject"):
        result = run(
            home, "pack", "export", "demo-service", "--format", fmt, "--out", str(tmp_path / fmt)
        )
        assert result.exit_code == 0, result.output
    assert (tmp_path / "md" / "demo-service.md").exists()
    assert "BEGIN INSTRUCTIONS" in (tmp_path / "inject" / "demo-service-inject.md").read_text()
