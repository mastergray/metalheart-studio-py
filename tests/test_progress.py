# Unit tests for the line-oriented task progress protocol

import json  # Build malformed and valid protocol fixtures

from metalheart.progress import PROGRESS_PREFIX  # Identify owned progress records
from metalheart.progress import buildProgressEvent  # Build deterministic timing fixtures
from metalheart.progress import formatDuration  # Format native status durations
from metalheart.progress import parseProgressLine  # Parse child-process output safely


# :: VOID -> NONE
# Verifies progress records round-trip with bounded counts and timing metadata
def testProgressEventRoundTrips() -> None:
    event = buildProgressEvent(
        "render",
        "rendering",
        27,
        100,
        "frames",
        10.0,
        "Completed chunk 2/8",
        24.5,
        {"chunk": 2, "chunks": 8, "scene": "impact"},
        15.25,
    )
    line = PROGRESS_PREFIX + json.dumps(event)
    parsed = parseProgressLine(line)
    assert parsed == event
    assert parsed["elapsed_sec"] == 5.25
    assert parsed["remaining_sec"] == 24.5
    assert parsed["context"]["scene"] == "impact"


# :: VOID -> NONE
# Verifies malformed and ordinary child output cannot become progress state
def testProgressParserRejectsUnownedOutput() -> None:
    assert parseProgressLine("[render] chunk 1/4 complete") is None
    assert parseProgressLine(PROGRESS_PREFIX + "not-json") is None
    assert parseProgressLine(PROGRESS_PREFIX + '{"task": "render"}') is None


# :: VOID -> NONE
# Verifies status durations stay compact across minute and hour boundaries
def testFormatsProgressDurations() -> None:
    assert formatDuration(0.0) == "00:00"
    assert formatDuration(65.4) == "01:05"
    assert formatDuration(3661.0) == "1:01:01"
