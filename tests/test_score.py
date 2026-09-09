from controlx.core.audit import detect_conflicts, score
from controlx.core.models import ProbeResult, Verdict


def result(verdict: Verdict, weight: float = 1.0) -> ProbeResult:
    return ProbeResult(probe_id="p", question="q", verdict=verdict, weight=weight)


def test_verdict_credit():
    assert Verdict.SUFFICIENT.credit == 1.0
    assert Verdict.PARTIAL.credit == 0.5
    assert Verdict.MISSING.credit == 0.0
    assert Verdict.CONFLICT.credit == 0.0


def test_score_is_weighted_average():
    results = [result(Verdict.SUFFICIENT), result(Verdict.PARTIAL), result(Verdict.MISSING)]
    assert score(results) == 50.0


def test_score_respects_weight():
    results = [result(Verdict.SUFFICIENT, weight=3.0), result(Verdict.MISSING, weight=1.0)]
    assert score(results) == 75.0


def test_score_of_nothing_is_zero():
    assert score([]) == 0.0


def test_conflict_detection(complete_pack, conflicting_pack, incomplete_pack):
    conflicts = detect_conflicts(complete_pack, conflicting_pack)
    assert [c.key for c in conflicts] == ["api_style"]
    assert conflicts[0].source_value == "REST only"
    assert conflicts[0].target_value == "GraphQL first"
    # a target that simply says nothing is a gap, not a contradiction
    assert detect_conflicts(complete_pack, incomplete_pack) == []
    assert detect_conflicts(complete_pack, None) == []
