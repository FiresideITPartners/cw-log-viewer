from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class LogEntry:
    """A single parsed log line from a Call Weaver log file.

    Fields:
        line_number: 1-based line number in the source file.
        raw: The original log line text.
        timestamp: Parsed datetime (year taken from parser config).
        level: Log level (VERBOSE, NOTICE, DTMF, ERROR, etc.).
        event_id: Numeric thread/process ID from the log.
        call_id: Call ID like C-00000052; None for lines without one.
        process: Source process name (e.g. pbx_lua.c).
        message: Everything after "process: ".
        dialed_number: From pbx_lua.c [dialed@context:pri] sub-format.
        context: Dialplan context from the sub-format.
        priority: Execution priority from the sub-format.
        action: Action name (NoOp, Dial, Goto, etc.).
        channel: SIP channel identifier.
        params: Action parameter string.
    """
    line_number: int
    raw: str
    timestamp: datetime
    level: str = ''
    event_id: int = 0
    call_id: Optional[str] = None
    process: str = ''
    message: str = ''

    # Parsed pbx_lua.c sub-fields (None if not a pbx_lua.c line or unparseable)
    dialed_number: Optional[str] = None
    context: Optional[str] = None
    priority: Optional[int] = None
    action: Optional[str] = None
    channel: Optional[str] = None
    params: Optional[str] = None