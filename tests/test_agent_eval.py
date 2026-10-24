"""CI runs the planted-error half of the eval harness: every planted error caught, every clean line passed."""

from tests.agent_eval import load_cases, planted


def test_every_planted_error_is_caught_and_every_clean_line_passes():
    report = planted(load_cases())
    assert report["moments"] >= 100
    assert report["caught"] == report["planted"], [r for r in report["rows"] if r["caught"] < r["planted"]]
    assert report["clean_passed"] == report["clean"], report["misses"]
    assert len(report["rows"]) >= 30
