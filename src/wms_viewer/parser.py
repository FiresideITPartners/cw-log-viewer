"""CallWeaver log file parser.

Parses the format:
  [Mon dd HH:MM:SS] LEVEL[event_id][call_id] process: message

And the pbx_lua.c sub-format:
  -- Executing [dialed@context:pri] Action("chan", "params")
"""

import re
from datetime import datetime

from .models import LogEntry

# Main line regex: [Jul 16 12:38:00] VERBOSE[778400][C-0000004a] pbx_lua.c: message
LINE_RE = re.compile(
    r'\[(?P<month>\w{3})\s+(?P<day>\d+)\s+(?P<time>\d{2}:\d{2}:\d{2})\]\s+'
    r'(?P<level>\w+)\[(?P<event_id>\d+)\](?:\[(?P<call_id>C-[0-9a-fA-F]+)\])?\s+'
    r'(?P<process>\S+):\s+(?P<message>.*)'
)

# pbx_lua.c executing sub-format
EXEC_RE = re.compile(
    r'--\s*Executing\s+\[(?P<bracket>[^\]]+)\]\s+'
    r'(?P<action>\w+)'
    r'\(\s*"(?P<channel>[^"]*)"\s*,\s*"(?P<params>.*)"\s*\)'
)

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}


class LogParser:
    """Parses CallWeaver log lines into LogEntry objects.

    Handles the top-level log line format and the pbx_lua.c
    Executing sub-format.  Provides line-by-line and whole-file
    parsing methods.
    """

    def __init__(self, year: int = 2026):
        self.year = year

    def parse_line(self, line_number: int, line: str) -> LogEntry:
        """Parse a single log line. Returns LogEntry with available fields filled."""
        line = line.rstrip('\n\r')

        m = LINE_RE.match(line)
        if not m:
            # Return UNKNOWN entry for unparseable lines
            return LogEntry(
                line_number=line_number,
                raw=line,
                timestamp=datetime.min,
                level='UNKNOWN',
                event_id=0,
            )

        # Parse timestamp
        month = MONTH_MAP.get(m.group('month'), 1)
        day = int(m.group('day'))
        hour, minute, sec = map(int, m.group('time').split(':'))
        ts = datetime(self.year, month, day, hour, minute, sec)

        entry = LogEntry(
            line_number=line_number,
            raw=line,
            timestamp=ts,
            level=m.group('level'),
            event_id=int(m.group('event_id')),
            call_id=m.group('call_id'),
            process=m.group('process'),
            message=m.group('message'),
        )

        # Parse pbx_lua.c executing sub-format if present
        self._parse_executing(entry)

        return entry

    def _parse_executing(self, entry: LogEntry) -> None:
        """Extract [dialed@context:pri] Action("chan", "params") if present."""
        m = EXEC_RE.search(entry.message)
        if not m:
            return

        entry.action = m.group('action')
        entry.channel = m.group('channel')
        entry.params = m.group('params')

        bracket = m.group('bracket')
        at_idx = bracket.rfind('@')
        if at_idx == -1:
            return

        entry.dialed_number = bracket[:at_idx]
        rest = bracket[at_idx + 1:]
        colon_idx = rest.rfind(':')
        if colon_idx == -1:
            entry.context = rest
            return

        entry.context = rest[:colon_idx]
        try:
            entry.priority = int(rest[colon_idx + 1:])
        except ValueError:
            entry.priority = None

    def parse_file(self, filepath: str) -> list[LogEntry]:
        """Parse an entire log file, returning all entries.

        Args:
            filepath: Path to the CallWeaver log file.

        Returns:
            List of LogEntry objects, one per line.
        """
        entries = []
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for i, line in enumerate(f, 1):
                entry = self.parse_line(i, line)
                entries.append(entry)
        return entries