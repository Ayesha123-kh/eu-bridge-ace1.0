import pytest

from app.services.patcher import PatchError, apply_findings, apply_patch


def test_exact_match():
    assert apply_patch("a\nb\nc", "b", "B") == "a\nB\nc"


def test_zero_match():
    with pytest.raises(PatchError, match="not found"):
        apply_patch("a\nb", "x", "y")


def test_multiple_match():
    with pytest.raises(PatchError, match="2 places"):
        apply_patch("x x", "x", "y")


def test_empty_original():
    with pytest.raises(PatchError):
        apply_patch("abc", "", "y")


def test_apply_findings_continues_after_failure_and_prefers_final_patch():
    fs = [
        {"id": "1", "original_snippet": "aaa", "suggested_patch": "AAA", "final_patch": "edited"},
        {"id": "2", "original_snippet": "missing", "suggested_patch": "z", "final_patch": None},
        {"id": "3", "original_snippet": "ccc", "suggested_patch": "CCC", "final_patch": None},
    ]
    content, res = apply_findings("aaa\nbbb\nccc", fs)
    assert content == "edited\nbbb\nCCC"
    assert res["1"] is None and res["3"] is None and "not found" in res["2"]
