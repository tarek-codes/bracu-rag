# RAG evaluation set

`questions.json` is a small, reviewable evaluation set built from the checked-in
knowledge-base documents under `output/`. It contains grounded BRAC University
questions with expected source files and answer anchors, plus out-of-scope
questions that must trigger the configured fallback.

Run the contract checks with:

```bash
uv run pytest tests/test_evaluation_set.py
```

The file is deliberately a fixture, not a source of university facts. When the
knowledge base or retrieval prompt changes, run the full evaluation workflow and
review source citations and fallback behavior before changing thresholds.
