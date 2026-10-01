# Line-oriented progress records shared by the CLI and native desktop application

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import json  # Encode progress as one robust machine-readable line
import sys  # Publish progress separately from ordinary command results
import time  # Measure elapsed work without wall-clock adjustments
from typing import Any, Dict, Optional  # Python 3.8-compatible event annotations


PROGRESS_PREFIX = "METALHEART_PROGRESS "


# :: STRING, STRING, INT, INT, STRING, FLOAT, STRING, FLOAT?, ARRAY<STRING, ANY>?, FLOAT? -> ARRAY<STRING, ANY>
# Builds one bounded progress event with elapsed and optional remaining time
def buildProgressEvent(
    task: str,
    phase: str,
    completed: int,
    total: int,
    unit: str,
    startedSec: float,
    message: str,
    remainingSec: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None,
    nowSec: Optional[float] = None,
) -> Dict[str, Any]:
    now = time.monotonic() if nowSec is None else nowSec
    boundedTotal = max(0, int(total))
    boundedCompleted = max(0, min(int(completed), boundedTotal))
    event: Dict[str, Any] = {
        "task": task,
        "phase": phase,
        "completed": boundedCompleted,
        "total": boundedTotal,
        "unit": unit,
        "elapsed_sec": round(max(0.0, now - startedSec), 3),
        "message": message,
    }
    if remainingSec is not None and remainingSec >= 0.0:
        event["remaining_sec"] = round(remainingSec, 3)
    if context:
        event["context"] = context
    return event


# :: BOOL, STRING, STRING, INT, INT, STRING, FLOAT, STRING, FLOAT?, ARRAY<STRING, ANY>? -> NONE
# Emits one progress record when the caller explicitly enables the protocol
def reportProgress(
    enabled: bool,
    task: str,
    phase: str,
    completed: int,
    total: int,
    unit: str,
    startedSec: float,
    message: str,
    remainingSec: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    if not enabled:
        return
    event = buildProgressEvent(
        task,
        phase,
        completed,
        total,
        unit,
        startedSec,
        message,
        remainingSec,
        context,
    )
    print(PROGRESS_PREFIX + json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)


# :: STRING -> ARRAY<STRING, ANY>?
# Parses one complete progress record and ignores ordinary process output
def parseProgressLine(line: str) -> Optional[Dict[str, Any]]:
    if not line.startswith(PROGRESS_PREFIX):
        return None
    try:
        event = json.loads(line[len(PROGRESS_PREFIX):])
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    required = ("task", "phase", "completed", "total", "unit", "elapsed_sec", "message")
    if any(name not in event for name in required):
        return None
    if isinstance(event["completed"], bool) or not isinstance(event["completed"], int):
        return None
    if isinstance(event["total"], bool) or not isinstance(event["total"], int):
        return None
    return event


# :: FLOAT -> STRING
# Formats elapsed and remaining seconds compactly for the native status area
def formatDuration(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))
    hours, remainder = divmod(rounded, 3600)
    minutes, secondsPart = divmod(remainder, 60)
    if hours:
        return "{0:d}:{1:02d}:{2:02d}".format(hours, minutes, secondsPart)
    return "{0:02d}:{1:02d}".format(minutes, secondsPart)
