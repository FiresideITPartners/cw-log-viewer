"""Tests for the CallFlow class — grouping, filtering, and summarization."""

import pytest
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from cw_viewer.parser import LogParser
from cw_viewer.callflow import CallFlow
from cw_viewer.models import LogEntry


@pytest.fixture(scope='module')
def _entries():
    parser = LogParser(year=2026)
    return parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )


@pytest.fixture
def callflow(_entries):
    return CallFlow(_entries)


# ── Grouping tests ──────────────────────────────────────────────────

def test_calls_are_grouped(callflow):
    """CallFlow groups entries by Call-ID."""
    assert len(callflow.calls) > 1
    for call_id in ['C-0000004a', 'C-0000004b', 'C-0000004c', 'C-0000004d',
                     'C-0000004e', 'C-0000004f', 'C-00000050', 'C-00000051',
                     'C-00000052']:
        assert call_id in callflow.calls, f"Missing {call_id}"


def test_noise_entries_separate(callflow):
    """Entries with no call_id go to callflow.noise."""
    assert len(callflow.noise) > 0
    assert all(e.call_id is None for e in callflow.noise)


def test_get_call(callflow):
    """get_call returns entries for a specific Call-ID."""
    call = callflow.get_call('C-0000004b')
    assert len(call) > 5
    assert any('Number Normalization' in e.message for e in call)


def test_call_ids_sorted(callflow):
    """sorted_call_ids returns IDs in hex-numeric order."""
    ids = callflow.sorted_call_ids()
    nums = [int(cid.split('-')[1], 16) for cid in ids]
    assert nums == sorted(nums)


# ── Filtering tests ─────────────────────────────────────────────────

def test_filter_entries_by_call_id(callflow):
    """filter_entries with call_id returns only that call's entries."""
    results = callflow.filter_entries(call_id='C-0000004a')
    assert len(results) > 0
    assert all(e.call_id == 'C-0000004a' for e in results)


def test_filter_entries_by_extension(callflow):
    """filter_entries with extension returns entries mentioning it."""
    results = callflow.filter_entries(extension='102')
    assert len(results) > 0
    assert all('102' in (e.message or '') for e in results)


def test_filter_entries_by_process(callflow):
    """filter_entries with process returns entries from that process."""
    results = callflow.filter_entries(process='app_dial.c')
    assert len(results) > 0
    assert all(e.process == 'app_dial.c' for e in results)


def test_filter_entries_by_time(callflow):
    """filter_entries with start/end returns entries in range."""
    start = datetime(2026, 7, 16, 12, 38, 0)
    end = datetime(2026, 7, 16, 12, 39, 0)
    results = callflow.filter_entries(start=start, end=end)
    assert len(results) > 0
    for e in results:
        if e.timestamp != datetime.min:
            assert start <= e.timestamp <= end


def test_filter_entries_exclude_noise(callflow):
    """filter_entries excludes config.c and res_awstranscribe.c by default."""
    results = callflow.filter_entries()
    assert all(e.process not in ('config.c', 'res_awstranscribe.c')
               for e in results)


def test_filter_entries_show_noise():
    """filter_entries with empty exclude_processes keeps all."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    cf = CallFlow(entries)
    results = cf.filter_entries(exclude_processes=[])
    has_config = any(e.process == 'config.c' for e in results)
    assert has_config  # should include noise processes


def test_filter_entries_combined(callflow):
    """Combined filters should work together."""
    start = datetime(2026, 7, 16, 12, 38, 0)
    end = datetime(2026, 7, 16, 12, 40, 0)
    results = callflow.filter_entries(
        call_id='C-0000004a',
        start=start,
        end=end,
    )
    assert len(results) > 0
    assert all(e.call_id == 'C-0000004a' for e in results)
    for e in results:
        if e.timestamp != datetime.min:
            assert start <= e.timestamp <= end


# ── Summary tests ───────────────────────────────────────────────────

def test_summarize_call_has_header(callflow):
    """summarize_call returns a formatted string with call info."""
    summary = callflow.summarize_call('C-0000004c')
    assert 'C-0000004c' in summary
    assert 'entries' in summary.lower() or '→' in summary


def test_summarize_call_missing_id(callflow):
    """summarize_call for missing call returns no-entries message."""
    summary = callflow.summarize_call('C-99999999')
    assert 'no entries' in summary.lower()


# ── Edge case tests ─────────────────────────────────────────────────

def test_empty_entries():
    """CallFlow with empty entries should work."""
    cf = CallFlow([])
    assert cf.calls == {}
    assert cf.noise == []
    assert cf.sorted_call_ids() == []
    assert cf.filter_entries() == []


def test_entries_only_call_ids():
    """All entries have call IDs — noise should be empty."""
    entries = [
        LogEntry(line_number=1, raw='', timestamp=datetime(2026, 7, 16, 12, 0, 0),
                 level='VERBOSE', event_id=1, call_id='C-00000001',
                 process='pbx_lua.c', message='test'),
    ]
    cf = CallFlow(entries)
    assert len(cf.calls) == 1
    assert cf.noise == []


def test_entries_only_noise():
    """All entries are noise (no call_id)."""
    entries = [
        LogEntry(line_number=1, raw='', timestamp=datetime(2026, 7, 16, 12, 0, 0),
                 level='VERBOSE', event_id=1, call_id=None,
                 process='config.c', message='Parsing config'),
    ]
    cf = CallFlow(entries)
    assert cf.calls == {}
    assert len(cf.noise) == 1


# ── Public filter helpers ───────────────────────────────────────────

def test_filter_by_extension_method(callflow):
    """filter_by_extension should match substrings in message."""
    results = callflow.filter_by_extension('102')
    assert len(results) > 0
    assert all('102' in (e.message or '') for e in results)


def test_filter_by_process_method(callflow):
    """filter_by_process should match exact process names."""
    results = callflow.filter_by_process('app_dial.c')
    assert len(results) > 0
    assert all(e.process == 'app_dial.c' for e in results)


def test_filter_by_time_method(callflow):
    """filter_by_time should include both bounds."""
    start = datetime(2026, 7, 16, 12, 38, 0)
    end = datetime(2026, 7, 16, 12, 39, 0)
    results = callflow.filter_by_time(start, end)
    assert len(results) > 0
    assert all(start <= e.timestamp <= end for e in results if e.timestamp != datetime.min)


def test_get_keys_for_call(callflow):
    """get_keys_for_call should extract human-readable call-flow steps."""
    keys = callflow.get_keys_for_call('C-0000004c')
    assert len(keys) > 0
    assert any('Dial:' in key or 'Route to:' in key or 'Caller:' in key for key in keys)