"""Output formatters for CW (Callweaver) log viewer.

Provides three formatting functions:
  - format_list_calls(cf)      Table of Call-IDs with start/end times
  - format_summary(cf, call_id=None)  Call-flow summary for one or all calls
  - format_raw(entries)        Filtered entries table
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Optional, TextIO

if TYPE_CHECKING:
    from .callflow import CallFlow
    from .models import LogEntry


def format_list_calls(
    cf: CallFlow,
    file: TextIO = sys.stdout,
    no_truncate: bool = False,
) -> None:
    """Print a table of all Call-IDs with start/end times and entry counts.

    Args:
        cf: A CallFlow instance with parsed and grouped entries.
        file: Output stream (default stdout).
        no_truncate: If True, print the full first message instead of
            truncating at 60 chars.
    """
    col_cid = 16
    col_time = 19
    col_count = 8
    header = (
        f"{'Call-ID':<{col_cid}} {'Start':>{col_time}} "
        f"{'End':>{col_time}} {'Entries':>{col_count}}  First Message"
    )
    print(header, file=file)
    print("-" * max(len(header), 80), file=file)

    for cid in cf.sorted_call_ids():
        call = cf.get_call(cid)
        if not call:
            continue
        first = call[0]
        last = call[-1]
        start = first.timestamp.strftime('%Y-%m-%d %H:%M:%S') if first.timestamp else '--:--:--'
        end = last.timestamp.strftime('%Y-%m-%d %H:%M:%S') if last.timestamp else '--:--:--'
        first_msg = (first.message or '')
        if not no_truncate:
            first_msg = first_msg[:60]
        print(
            f"{cid:<{col_cid}} {start:>{col_time}} "
            f"{end:>{col_time}} {len(call):>{col_count}}  {first_msg}",
            file=file,
        )


def format_summary(
    cf: CallFlow,
    call_id: Optional[str] = None,
    start: Optional["datetime"] = None,
    end: Optional["datetime"] = None,
    file: TextIO = sys.stdout,
) -> None:
    """Print a call-flow summary for one call or all calls.

    Args:
        cf: A CallFlow instance with parsed and grouped entries.
        call_id: Specific Call-ID to summarize (None = all calls).
        start: Start datetime filter (optional).
        end: End datetime filter (optional).
        file: Output stream (default stdout).

    Prints CallFlow.summarize_call(cid) for each matching call.
    Call-IDs without entries in cf.calls are silently skipped.
    When start/end are provided, calls entirely outside the window are
    excluded (i.e. if every entry's timestamp is outside the range).
    """
    from datetime import datetime as dt

    call_ids = [call_id] if call_id else cf.sorted_call_ids()

    for cid in call_ids:
        if cid not in cf.calls:
            continue

        call_entries = cf.get_call(cid)
        timestamps = [e.timestamp for e in call_entries if e.timestamp]

        # Time-filter: skip calls entirely outside window
        if start and timestamps and all(t < start for t in timestamps):
            continue
        if end and timestamps and all(t > end for t in timestamps):
            continue

        print(cf.summarize_call(cid), file=file)


def format_raw(
    entries: list[LogEntry],
    file: TextIO = sys.stdout,
    no_truncate: bool = False,
) -> None:
    """Print a table of filtered log entries.

    Args:
        entries: Filtered list of LogEntry objects.
        file: Output stream (default stdout).
        no_truncate: If True, print the full message instead of
            truncating at 80 chars.
    """
    if not entries:
        print("(no entries)", file=file)
        return

    print(
        f"{'Time':>19} {'Level':<8} {'Call-ID':<14} {'Process':<25} Message",
        file=file,
    )
    print("-" * 120, file=file)

    for e in entries:
        ts = e.timestamp.strftime('%Y-%m-%d %H:%M:%S') if e.timestamp else '--:--:--'
        cid = e.call_id or '-'
        msg = (e.message or '')
        if not no_truncate:
            msg = msg[:80]
        print(
            f"{ts:>19} {e.level or '':<8} {cid:<14} "
            f"{e.process or '':<25} {msg}",
            file=file,
        )

    print(file=file)
    print(f"--- {len(entries)} entries shown ---", file=file)


def format_csv(entries: list[LogEntry], file: TextIO = sys.stdout) -> None:
    """Write filtered log entries as CSV to stdout.

    Columns: line_number, timestamp (YYYY-MM-DD HH:MM:SS), level,
    event_id, call_id, process, dialed_number, context, priority,
    action, channel, params, message.

    Args:
        entries: Filtered list of LogEntry objects.
        file: Output stream (default stdout).
    """
    writer = csv.writer(file, lineterminator='\n')
    writer.writerow([
        'line_number', 'timestamp', 'level', 'event_id', 'call_id',
        'process', 'dialed_number', 'context', 'priority', 'action',
        'channel', 'params', 'message',
    ])

    for e in entries:
        writer.writerow([
            e.line_number,
            e.timestamp.strftime('%Y-%m-%d %H:%M:%S') if e.timestamp and e.timestamp != datetime.min else '',
            e.level or '',
            e.event_id,
            e.call_id or '',
            e.process or '',
            e.dialed_number or '',
            e.context or '',
            e.priority if e.priority is not None else '',
            e.action or '',
            e.channel or '',
            e.params or '',
            (e.message or '').replace('\n', ' ').replace('\r', ''),
        ])