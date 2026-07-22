"""Tests for the LogParser class — line parsing and file parsing."""

import pytest
from datetime import datetime
from pathlib import Path

# We're in tests/ directory, need to add src/ to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from wms_viewer.parser import LogParser
from wms_viewer.models import LogEntry


# ── Line parsing tests ─────────────────────────────────────────────

def test_parse_basic_pbx_lua_line():
    """Parse a pbx_lua.c line with Executing sub-format."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 13:05:20] VERBOSE[788916][C-00000052] pbx_lua.c:     '
        '-- Executing [104@internalcalls:1] NoOp("Local/104@internalcalls-0000002b;2", '
        '"Device state for \'SIP/104\' is NOT_INUSE")'
    )
    assert entry.timestamp == datetime(2026, 7, 16, 13, 5, 20)
    assert entry.level == 'VERBOSE'
    assert entry.event_id == 788916
    assert entry.call_id == 'C-00000052'
    assert entry.process == 'pbx_lua.c'
    assert entry.dialed_number == '104'
    assert entry.context == 'internalcalls'
    assert entry.priority == 1
    assert entry.action == 'NoOp'
    assert entry.channel == 'Local/104@internalcalls-0000002b;2'


def test_parse_non_pbx_lua_line():
    """Parse a non-pbx_lua line — should not have action sub-fields."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:39:04] VERBOSE[778989][C-0000004b] app_dial.c:     -- SIP/104-0000008b is ringing'
    )
    assert entry.process == 'app_dial.c'
    assert entry.call_id == 'C-0000004b'
    assert entry.action is None
    assert entry.dialed_number is None


def test_parse_no_call_id():
    """Parse a config.c line with no call_id."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:39:27] VERBOSE[4817] config.c:   == Parsing config'
    )
    assert entry.call_id is None
    assert entry.process == 'config.c'
    assert entry.level == 'VERBOSE'
    assert entry.event_id == 4817


def test_parse_dtmf_line():
    """Parse a line with DTMF log level."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:38:58] DTMF[778743][C-0000004b] channel.c: DTMF begin \'0\' received on SIP/classound-0000008a'
    )
    assert entry.level == 'DTMF'
    assert entry.call_id == 'C-0000004b'
    assert entry.process == 'channel.c'
    assert 'DTMF begin' in entry.message


def test_parse_warning_level():
    """Parse a WARNING level line."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:39:10] WARNING[778989][C-0000004b] app_dial.c: Something worth warning about'
    )
    assert entry.level == 'WARNING'
    assert entry.call_id == 'C-0000004b'
    assert entry.process == 'app_dial.c'
    assert entry.message == 'Something worth warning about'


def test_parse_empty_line():
    """An empty line should return a UNKNOWN-level entry."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(1, '')
    assert entry.level == 'UNKNOWN'
    assert entry.timestamp == datetime.min
    assert entry.event_id == 0
    assert entry.raw == ''


def test_parse_ivr_context_without_priority():
    """Parse a pbx_lua.c line with dialed@context but no :priority suffix."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:38:00] VERBOSE[778400][C-0000004a] pbx_lua.c:     '
        '-- Executing [IVR@IVR 801] NoOp("SIP/classound-00000088", "Executing IVR")'
    )
    assert entry.dialed_number == 'IVR'
    assert entry.context == 'IVR 801'
    assert entry.priority is None
    assert entry.action == 'NoOp'


def test_parse_app_queue_nobody_picked_up():
    """Parse an app_queue.c timeout line."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:38:00] VERBOSE[778400][C-0000004a] app_queue.c:     -- Nobody picked up in 20000 ms'
    )
    assert entry.process == 'app_queue.c'
    assert entry.call_id == 'C-0000004a'
    assert 'Nobody picked up' in entry.message


def test_parse_notice_level():
    """Parse a NOTICE level line."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:38:10] NOTICE[778400][C-0000004a] chan_sip.c: trunk_calls_count decremented and now its value is 0'
    )
    assert entry.level == 'NOTICE'
    assert entry.process == 'chan_sip.c'


def test_parse_dial_action():
    """Parse a pbx_lua.c Dial action line."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 13:05:20] VERBOSE[789017][C-00000052] pbx_lua.c:     '
        '-- Executing [104@internalcalls:1] Dial("Local/104@internalcalls-0000002b;2", '
        '"SIP/104,20,zb(predial^internalcall^1(,<http://127.0.0.1/Ring1.wav;info=external>,6,classound,,4597215,false))")'
    )
    assert entry.action == 'Dial'
    assert entry.dialed_number == '104'
    assert entry.context == 'internalcalls'
    assert entry.priority == 1
    assert 'SIP/104' in entry.params


def test_parse_ivr_context():
    """Parse a line with IVR context that has a space in it."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:38:00] VERBOSE[778400][C-0000004a] pbx_lua.c:     '
        '-- Executing [2@IVR 801:1] NoOp("SIP/classound-00000088", '
        '"Executing \'Playback\': sound - \\"00000/DayTimeMainMenu\\", waitDigits - n, opts - ")'
    )
    assert entry.dialed_number == '2'
    assert entry.context == 'IVR 801'
    assert entry.priority == 1
    assert entry.action == 'NoOp'


def test_parse_without_priority():
    """Parse a pbx_lua.c line that only has dialed@context (no :priority)."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(
        1,
        '[Jul 16 12:38:55] VERBOSE[778743][C-0000004b] pbx_lua.c:     '
        '-- Executing [+178****3935@classound:1] NoOp("SIP/classound-0000008a", "Set call class")'
    )
    assert entry.dialed_number == '+178****3935'
    assert entry.context == 'classound'
    assert entry.priority == 1


def test_parse_unparseable_line():
    """An unparseable line should return a UNKNOWN-level entry."""
    parser = LogParser(year=2026)
    entry = parser.parse_line(1, 'this is not a log line at all')
    assert entry.level == 'UNKNOWN'
    assert entry.timestamp == datetime.min
    assert entry.event_id == 0
    assert entry.raw == 'this is not a log line at all'


# ── parse_file tests ───────────────────────────────────────────────

def test_parse_file_basic():
    """parse_file should return a list of LogEntry objects."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    # The file has 500 non-empty lines (first line is truncated: missing '[')
    assert len(entries) == 500
    assert all(isinstance(e, LogEntry) for e in entries)

    # First line is malformed (missing '[') — it should be UNKNOWN
    first = entries[0]
    assert first.level == 'UNKNOWN'

    # Second line is valid
    second = entries[1]
    assert 'Executing' in second.message
    assert second.process == 'pbx_lua.c'


def test_parse_file_call_ids():
    """All entries with call-id should have it in the call_id field."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    call_entries = [e for e in entries if e.call_id]
    assert len(call_entries) > 400  # most have call IDs

    # Check a specific known call
    calls_4a = [e for e in entries if e.call_id == 'C-0000004a']
    assert len(calls_4a) > 5


def test_parse_file_pbx_lua_have_dialed():
    """pbx_lua.c entries should have dialed_number where Executing is present."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    lua_entries = [e for e in entries if e.process == 'pbx_lua.c']
    assert len(lua_entries) > 20

    with_dialed = [e for e in lua_entries if e.dialed_number]
    assert len(with_dialed) > 10

    dialed_values = {e.dialed_number for e in with_dialed}
    assert '104' in dialed_values


def test_parse_file_timestamps_sequential():
    """Timestamps should be valid datetimes and generally increasing."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    # Verify timestamps are parseable
    for e in entries:
        assert isinstance(e.timestamp, datetime)
        assert e.timestamp != datetime.min or e.level == 'UNKNOWN'

    # First entry is malformed (missing '['), second is valid
    assert entries[0].level == 'UNKNOWN'
    assert entries[1].timestamp == datetime(2026, 7, 16, 12, 38, 0)


# ── Filtering tests ────────────────────────────────────────────────

def test_filter_by_extension():
    """Filtering by extension substring should work."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    # Manually filter (this is what the module should do)
    ext_102 = [e for e in entries if '102' in (e.message or '')]
    assert len(ext_102) > 0
    # All should mention 102
    assert all('102' in (e.message or '') for e in ext_102)


def test_filter_by_call_id():
    """Filtering by exact call-id."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    c4a = [e for e in entries if e.call_id == 'C-0000004a']
    assert len(c4a) > 5
    assert all(e.call_id == 'C-0000004a' for e in c4a)


def test_filter_by_process():
    """Filtering by process name."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    dial = [e for e in entries if e.process == 'app_dial.c']
    assert len(dial) > 0
    assert all(e.process == 'app_dial.c' for e in dial)


def test_filter_by_time_range():
    """Filtering by time range (inclusive)."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    start = datetime(2026, 7, 16, 12, 38, 0)
    end = datetime(2026, 7, 16, 12, 39, 0)
    in_range = [e for e in entries
                if e.timestamp != datetime.min
                and start <= e.timestamp <= end]
    assert len(in_range) > 0
    assert all(start <= e.timestamp <= end for e in in_range if e.timestamp != datetime.min)


def test_filter_noise_exclusion():
    """config.c and res_awstranscribe.c entries should be excludable."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    # Count noise entries
    noise = [e for e in entries if e.process in ('config.c', 'res_awstranscribe.c')]
    assert len(noise) > 0  # there should be some

    # Excluding them should reduce count
    cleaned = [e for e in entries if e.process not in ('config.c', 'res_awstranscribe.c')]
    assert len(cleaned) < len(entries)
    assert all(e.process not in ('config.c', 'res_awstranscribe.c') for e in cleaned)


def test_default_year_2026():
    """Default year should be 2026."""
    parser = LogParser()
    assert parser.year == 2026

    parser2 = LogParser(year=2025)
    assert parser2.year == 2025