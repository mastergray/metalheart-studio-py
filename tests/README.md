# Test Suite

The test levels, fixtures, coverage thresholds, synchronization requirements, and golden-update policy are defined in section 14 of `docs/metalheart-studio-spec.md`.

Production test modules use `test_*.py`; test functions use a camelCase `test...` prefix so pytest discovery remains compatible with the project's Python naming standard.

Markers configured in `pyproject.toml`:

- `integration` for FFmpeg, cache, adapter, and assembly tests;
- `visual` for reviewed frame or clip regressions;
- `slow` for complete renders, concurrency, cancellation, and recovery.

Reference files under `ref/` are test inputs and baselines, not production modules.

Run the complete default suite from the repository root with:

```bash
uv run --with pytest --with pytest-asyncio pytest
```

Focused and release-oriented selections use the same environment:

```bash
uv run --with pytest --with pytest-asyncio pytest tests/test_ui.py
uv run --with pytest --with pytest-asyncio pytest -m "integration or visual"
uv run --with pytest --with pytest-asyncio pytest -m slow
```

The full local release pass additionally requires the machine's Python 3.8 runtime and the documented FFmpeg tools. Tests that require an unavailable optional binary must skip with a precise reason rather than silently passing.

