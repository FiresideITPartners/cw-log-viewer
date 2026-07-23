"""Unit tests for output_formatter module."""
import io
import pytest

from src.wms_viewer.parser import LogParser
from src.wms_viewer.callflow import CallFlow
from src.wms_viewer.output_formatter import (
    format_list_calls,
    format_summary,
    format_raw,
)


@pytest.fixture(scope="module")
def callflow():
    """Load the full test dataset once."""
    lp = LogParser(year=2026)
    entries = lp.parse_file("cwtrunc.txt")
    return CallFlow(entries)


# ── format_list_calls ──────────────────────────────────────────────

class TestFormatListCalls:
    """Tests for format_list_calls(cf)."""

    def test_header_present(self, callflow):
        buf = io.StringIO()
        format_list_calls(callflow, file=buf)
        out = buf.getvalue()
        assert "Call-ID" in out
        assert "Start" in out
        assert "End" in out
        assert "Entries" in out
        assert "First Message" in out

    def test_all_nine_calls_in_output(self, callflow):
        buf = io.StringIO()
        format_list_calls(callflow, file=buf)
        out = buf.getvalue()
        for cid in (f"C-0000004{i}" for i in ['a', 'b', 'c', 'd', 'e', 'f']):
            assert cid in out
        assert "C-00000050" in out
        assert "C-00000051" in out
        assert "C-00000052" in out

    def test_calls_sorted_by_hex(self, callflow):
        buf = io.StringIO()
        format_list_calls(callflow, file=buf)
        out = buf.getvalue()
        # Find positions of Call-IDs in output
        a_pos = out.index("C-0000004a")
        b_pos = out.index("C-0000004b")
        c_pos = out.index("C-0000004c")
        d_pos = out.index("C-0000004d")
        assert a_pos < b_pos < c_pos < d_pos

    def test_shows_entry_counts(self, callflow):
        buf = io.StringIO()
        format_list_calls(callflow, file=buf)
        out = buf.getvalue()
        assert "18" in out   # C-0000004a
        assert "56" in out   # C-0000004b
        assert "50" in out   # C-0000004c

    def test_timestamps_in_hhmmss(self, callflow):
        buf = io.StringIO()
        format_list_calls(callflow, file=buf)
        out = buf.getvalue()
        assert "12:38:00" in out
        assert "12:38:10" in out
        assert "13:05:06" in out
        assert "13:05:36" in out


# ── format_summary ──────────────────────────────────────────────────

class TestFormatSummary:
    """Tests for format_summary(cf, call_id=...)."""

    def test_single_call_id_produces_one_block(self, callflow):
        buf = io.StringIO()
        format_summary(callflow, call_id="C-0000004c", file=buf)
        out = buf.getvalue()
        assert out.count("Call C-") == 1
        assert "C-0000004c" in out

    def test_all_calls_without_call_id(self, callflow):
        buf = io.StringIO()
        format_summary(callflow, file=buf)
        out = buf.getvalue()
        assert out.count("Call C-") == 9

    def test_specific_call_has_key_details(self, callflow):
        buf = io.StringIO()
        format_summary(callflow, call_id="C-0000004c", file=buf)
        out = buf.getvalue()
        assert "👤 Caller: Anonymous" in out
        assert "📞 Dial: 102" in out
        assert "✅ Answered" in out
        assert "📞 Trunk call started" in out
        assert "📴 Trunk ended" in out

    def test_unknown_call_id_silently_skipped(self, callflow):
        buf = io.StringIO()
        format_summary(callflow, call_id="C-DEADBEEF", file=buf)
        out = buf.getvalue()
        assert "Call C-" not in out
        assert out == "" or out.isspace() or out.strip() == ""

    def test_time_filter_excludes_calls_outside_window(self, callflow):
        from datetime import datetime
        # Only C-0000004a and C-0000004b should be in this window
        start = datetime(2026, 7, 16, 12, 38, 0)
        end = datetime(2026, 7, 16, 12, 39, 30)
        buf = io.StringIO()
        format_summary(callflow, start=start, end=end, file=buf)
        out = buf.getvalue()
        assert "C-0000004a" in out
        assert "C-0000004b" in out
        assert "C-0000004c" not in out   # starts at 12:39:32

    def test_empty_start_filter_includes_everything(self, callflow):
        from datetime import datetime
        end = datetime(2026, 7, 16, 12, 00, 0)
        buf = io.StringIO()
        format_summary(callflow, end=end, file=buf)
        out = buf.getvalue()
        # No calls before 12:00, all start at 12:38+
        assert "Call C-" not in out or out.strip() == ""

    def test_empty_end_filter_includes_remaining(self, callflow):
        from datetime import datetime
        start = datetime(2026, 7, 16, 14, 0, 0)
        buf = io.StringIO()
        format_summary(callflow, start=start, file=buf)
        out = buf.getvalue()
        # No calls after 14:00, last is 13:05:36
        assert "Call C-" not in out or out.strip() == ""


# ── format_raw ──────────────────────────────────────────────────────

class TestFormatRaw:
    """Tests for format_raw(entries)."""

    def test_header_present(self, callflow):
        filtered = callflow.filter_entries(exclude_processes=[])
        buf = io.StringIO()
        format_raw(filtered, file=buf)
        out = buf.getvalue()
        assert "Time" in out
        assert "Level" in out
        assert "Call-ID" in out
        assert "Process" in out
        assert "Message" in out

    def test_shows_entry_count(self, callflow):
        filtered = callflow.filter_entries(exclude_processes=[])
        buf = io.StringIO()
        format_raw(filtered, file=buf)
        out = buf.getvalue()
        assert f"{len(filtered)} entries shown" in out

    def test_empty_list_shows_message(self, callflow):
        buf = io.StringIO()
        format_raw([], file=buf)
        out = buf.getvalue()
        assert "(no entries)" in out

    def test_entries_have_timestamps(self, callflow):
        filtered = callflow.filter_entries(exclude_processes=[])
        buf = io.StringIO()
        format_raw(filtered, file=buf)
        out = buf.getvalue()
        assert "12:38:" in out
        assert "13:05:" in out

    def test_call_id_column_shows_ids(self, callflow):
        filtered = callflow.filter_entries(call_id="C-0000004a")
        buf = io.StringIO()
        format_raw(filtered, file=buf)
        out = buf.getvalue()
        lines = [l for l in out.split("\n") if "C-0000004a" in l.split()[:6]]
        assert len(lines) > 0


# ── Integration: wiring through wms_viewer.py CLI ───────────────────

class TestCLIIntegration:
    """Verify the formatters integrate correctly through the CLI."""

    def test_list_calls_via_cli(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "wms_viewer.py", "cwtrunc.txt", "--list-calls"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Call-ID" in result.stdout
        assert "C-0000004a" in result.stdout
        assert "C-00000052" in result.stdout

    def test_summary_single_call_via_cli(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "wms_viewer.py", "cwtrunc.txt",
             "--summary", "--call-id", "C-0000004c"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Call C-0000004c" in result.stdout
        assert "Anonymous" in result.stdout
        assert "📞 Dial: 102" in result.stdout

    def test_summary_all_calls_via_cli(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "wms_viewer.py", "cwtrunc.txt", "--summary"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert result.stdout.count("Call C-") == 9

    def test_raw_default_via_cli(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "wms_viewer.py", "cwtrunc.txt"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Time" in result.stdout
        assert "entries shown" in result.stdout
        # 500 entries - 70 noise = 430
        assert "430 entries shown" in result.stdout

    def test_time_filtered_raw_via_cli(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "wms_viewer.py", "cwtrunc.txt",
             "--from", "12:38", "--to", "12:40"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "115 entries shown" in result.stdout