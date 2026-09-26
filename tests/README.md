# Test Suite

The test levels, fixtures, coverage thresholds, synchronization requirements, and golden-update policy are defined in section 14 of `docs/metalheart-studio-spec.md`.

Production test modules use `test_*.py`; test functions use a camelCase `test...` prefix so pytest discovery remains compatible with the project's Python naming standard.

Markers configured in `pyproject.toml`:

- `integration` for FFmpeg, cache, adapter, and assembly tests;
- `visual` for reviewed frame or clip regressions;
- `slow` for complete renders, concurrency, cancellation, and recovery.

Reference files under `ref/` are test inputs and baselines, not production modules.

