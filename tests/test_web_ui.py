"""Tests for --serve flag and web UI integration."""

import json
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from cw_viewer.web_ui import serve, CallFlowHandler  # noqa: E402
from cw_viewer.parser import LogParser  # noqa: E402
from cw_viewer.callflow import CallFlow  # noqa: E402


# ── CLI argument tests (no server needed) ────────────────────────────

def test_serve_is_mutually_exclusive_with_list_calls():
    """--serve and --list-calls together should fail."""
    result = subprocess.run(
        [sys.executable, "cw_viewer.py", "cwtrunc.txt", "--serve", "--list-calls"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_serve_is_mutually_exclusive_with_summary():
    """--serve and --summary together should fail."""
    result = subprocess.run(
        [sys.executable, "cw_viewer.py", "cwtrunc.txt", "--serve", "--summary"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_serve_is_mutually_exclusive_with_csv():
    """--serve and --csv together should fail."""
    result = subprocess.run(
        [sys.executable, "cw_viewer.py", "cwtrunc.txt", "--serve", "--csv"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_serve_short_flag_w_works():
    """-w should be the short form of --serve."""
    result = subprocess.run(
        [sys.executable, "cw_viewer.py", "--help"],
        capture_output=True, text=True,
    )
    assert "--serve" in result.stdout or "-w" in result.stdout


def test_serve_with_port():
    """--serve --port 9999 should be accepted."""
    result = subprocess.run(
        [sys.executable, "cw_viewer.py", "--help"],
        capture_output=True, text=True,
    )
    assert "--port" in result.stdout


def test_default_port_is_8080():
    """Default port should be 8080."""
    result = subprocess.run(
        [sys.executable, "cw_viewer.py", "--help"],
        capture_output=True, text=True,
    )
    assert "8080" in result.stdout


def test_serve_with_host():
    """--host should be accepted."""
    result = subprocess.run(
        [sys.executable, "cw_viewer.py", "--help"],
        capture_output=True, text=True,
    )
    assert "--host" in result.stdout


# ── Server fixture (module-scoped, one server for all API tests) ─────

@pytest.fixture(scope="module")
def server_url():
    """Start a real HTTP server on an OS-assigned port, return base URL."""
    parser = LogParser(year=2026)
    entries = parser.parse_file(
        str(Path(__file__).parent.parent / 'cwtrunc.txt')
    )
    cf = CallFlow(entries)

    import http.server
    import socketserver

    class Handler(CallFlowHandler):
        pass
    Handler.callflow = cf

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()


# ── API endpoint tests ───────────────────────────────────────────────

def test_api_calls_returns_json(server_url):
    """GET /api/calls returns JSON array of call summaries."""
    url = f"{server_url}/api/calls"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read())
    assert isinstance(data, list)
    assert len(data) == 9


def test_api_calls_has_required_fields(server_url):
    """Each call object has id, date, start, end, entries, caller, destination."""
    url = f"{server_url}/api/calls"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    call = data[0]
    assert 'id' in call
    assert 'date' in call
    assert isinstance(call['date'], str)
    assert 'start' in call
    assert 'end' in call
    assert 'entries' in call
    assert 'caller' in call
    assert 'destination' in call
    assert call['id'].startswith('C-000000')


def test_api_call_detail_returns_events(server_url):
    """GET /api/calls/<id> returns call details with events array."""
    url = f"{server_url}/api/calls/C-0000004c"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read())
    assert data['id'] == 'C-0000004c'
    assert 'events' in data
    assert len(data['events']) > 0
    event = data['events'][0]
    assert 'time' in event
    assert 'label' in event


def test_api_call_detail_404(server_url):
    """GET /api/calls/<missing-id> returns 404."""
    url = f"{server_url}/api/calls/C-DEADBEEF"
    try:
        urllib.request.urlopen(url)
        assert False, "Should have raised HTTPError"
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_api_entries_filtering(server_url):
    """GET /api/entries?extension=102 returns matching entries."""
    url = f"{server_url}/api/entries?extension=102"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    assert isinstance(data, list)
    assert len(data) > 0
    assert all('102' in (e.get('message', '')) for e in data)


def test_api_entries_filter_by_call_id(server_url):
    """GET /api/entries?call_id=C-0000004a returns only that call's entries."""
    url = f"{server_url}/api/entries?call_id=C-0000004a"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    assert len(data) > 0
    assert all(e['call_id'] == 'C-0000004a' for e in data)


def test_api_calls_sorted(server_url):
    """GET /api/calls returns calls sorted by hex Call-ID."""
    url = f"{server_url}/api/calls"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    ids = [c['id'] for c in data]
    nums = [int(cid.split('-')[1], 16) for cid in ids]
    assert nums == sorted(nums)


def test_api_serve_html_page(server_url):
    """GET / returns the HTML page."""
    url = f"{server_url}/"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        content_type = resp.headers.get('Content-Type', '')
        assert 'text/html' in content_type
        body = resp.read().decode('utf-8')
    assert '<title>' in body
    assert '</html>' in body


def test_api_entries_max_200(server_url):
    """GET /api/entries caps at 200 results."""
    url = f"{server_url}/api/entries"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    assert len(data) <= 200


def test_api_call_detail_events_have_raw_text(server_url):
    """Each event in call detail has raw message and process fields."""
    url = f"{server_url}/api/calls/C-0000004c"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    assert 'events' in data
    assert len(data['events']) > 0
    for event in data['events']:
        assert 'raw' in event, f"Event missing 'raw': {event}"
        assert 'process' in event, f"Event missing 'process': {event}"
        assert isinstance(event['raw'], str)
        assert isinstance(event['process'], str)


def test_api_call_detail_has_date(server_url):
    """GET /api/calls/<id> returns a valid date field (e.g. 'Jul 16')."""
    url = f"{server_url}/api/calls/C-0000004c"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    assert 'date' in data
    assert isinstance(data['date'], str)
    # Should be month abbreviation + day
    import re
    assert re.match(r'^[A-Z][a-z]{2} \d{1,2}$', data['date']), f"Unexpected date format: {data['date']}"