import json
from pathlib import Path
from typing import Any

EVAL_FILE = Path(__file__).parent / "eval" / "questions.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_KEYS = {"id", "question", "expected_sources", "answer_must_include", "must_fallback"}


def test_evaluation_set_is_grounded_and_complete() -> None:
    cases: list[dict[str, Any]] = json.loads(EVAL_FILE.read_text(encoding="utf-8"))

    assert len(cases) >= 8
    assert len({case["id"] for case in cases}) == len(cases)
    assert any(case["must_fallback"] for case in cases)
    assert any(not case["must_fallback"] for case in cases)

    for case in cases:
        assert set(case) == REQUIRED_KEYS
        assert case["question"].strip()
        assert isinstance(case["expected_sources"], list)
        assert isinstance(case["answer_must_include"], list)
        if case["must_fallback"]:
            assert case["expected_sources"] == []
            assert case["answer_must_include"] == []
        else:
            assert case["expected_sources"]
            for source in case["expected_sources"]:
                assert (REPOSITORY_ROOT / source).is_file(), f"Missing evaluation source: {source}"
