from __future__ import annotations

from pathlib import Path

import pytest

from controlx.context import AppContext
from controlx.core.models import Constraint, Pack, Probe
from controlx.services import EXAMPLES_DIR, import_pack, init_home

COMPLETE_INSTRUCTIONS = """## Alpha

- The alpha rule is that widgets are immutable.

## Beta

- The beta rule is that every request carries a trace id.
"""

INCOMPLETE_INSTRUCTIONS = """## Alpha

- The alpha rule is that widgets are immutable.
"""


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cxhome"
    monkeypatch.setenv("CONTROLX_HOME", str(root))
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    init_home(root)
    return root


@pytest.fixture()
def ctx(home: Path) -> AppContext:
    context = AppContext.load(home)
    yield context
    context.close()


@pytest.fixture()
def complete_pack() -> Pack:
    return Pack(
        slug="complete",
        name="Complete",
        instructions=COMPLETE_INSTRUCTIONS,
        constraints=[Constraint(key="api_style", value="REST only")],
        probes=[
            Probe(
                id="prb_alpha",
                question="What is the alpha rule?",
                expected_signals=["widgets are immutable"],
            ),
            Probe(
                id="prb_beta",
                question="What is the beta rule?",
                expected_signals=["every request carries a trace id"],
            ),
        ],
    )


@pytest.fixture()
def incomplete_pack() -> Pack:
    return Pack(slug="incomplete", name="Incomplete", instructions=INCOMPLETE_INSTRUCTIONS)


@pytest.fixture()
def conflicting_pack() -> Pack:
    return Pack(
        slug="conflicting",
        name="Conflicting",
        instructions=INCOMPLETE_INSTRUCTIONS,
        constraints=[Constraint(key="api_style", value="GraphQL first")],
    )


@pytest.fixture()
def demo_ctx(ctx: AppContext) -> AppContext:
    """Context with both shipped example packs imported."""
    for slug in ("demo-service", "demo-thin"):
        import_pack(ctx, EXAMPLES_DIR / slug)
    return ctx


@pytest.fixture(autouse=True)
def _no_clipboard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("controlx.services.copy_to_clipboard", lambda text: False)
