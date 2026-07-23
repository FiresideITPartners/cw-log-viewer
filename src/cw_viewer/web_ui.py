"""Web UI server for the CW (Callweaver) Log Viewer.

Provides a local HTTP server with REST API endpoints and a single-page
browseable UI.  No external dependencies — stdlib only.
"""

from __future__ import annotations

import json
import re
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .callflow import CallFlow


_HTML_PAGE = '''\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CW (Callweaver) Log Viewer</title>
<style>
  :root {
    --bg: #1a1a2e;
    --sidebar-bg: #16213e;
    --card-bg: #0f3460;
    --text: #e0e0e0;
    --muted: #8892b0;
    --accent: #e94560;
    --green: #00b894;
    --border: #2d3748;
    --hover: #1a365d;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); display: flex; height: 100vh; }
  #sidebar { width: 320px; min-width: 280px; background: var(--sidebar-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  #sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); }
  #sidebar-header h1 { font-size: 1.1rem; font-weight: 600; color: var(--accent); margin-bottom: 4px; }
  #sidebar-header .subtitle { font-size: 0.75rem; color: var(--muted); }
  #filters { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; gap: 6px; flex-wrap: wrap; }
  #filters input, #filters select { background: var(--card-bg); border: 1px solid var(--border); color: var(--text); padding: 6px 10px; border-radius: 4px; font-size: 0.8rem; width: 100%; }
  #filters input::placeholder { color: var(--muted); }
  #call-list { flex: 1; overflow-y: auto; }
  .call-item { padding: 12px 16px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.15s; }
  .call-item:hover { background: var(--hover); }
  .call-item.active { background: var(--card-bg); border-left: 3px solid var(--accent); }
  .call-item .cid { font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 0.85rem; font-weight: 600; color: var(--accent); margin-bottom: 2px; }
  .call-item .meta { font-size: 0.75rem; color: var(--muted); }
  .call-item .meta span { margin-right: 10px; }
  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #main-header { padding: 16px 24px; border-bottom: 1px solid var(--border); }
  #main-header h2 { font-size: 1.2rem; font-weight: 600; }
  #main-header .details { font-size: 0.8rem; color: var(--muted); margin-top: 4px; }
  #timeline { flex: 1; overflow-y: auto; padding: 24px; }
  .tl-event { display: flex; align-items: flex-start; padding: 6px 0; position: relative; }
  .tl-event.clickable { cursor: pointer; border-radius: 4px; }
  .tl-event.clickable:hover { background: var(--hover); }
  .tl-event:not(:last-child)::before { content: ''; position: absolute; left: 45px; top: 28px; bottom: -6px; width: 2px; background: var(--border); }
  .tl-raw { font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 0.7rem; color: var(--muted); margin-left: 92px; padding: 4px 8px; background: var(--card-bg); border-radius: 4px; margin-top: 2px; margin-bottom: 4px; display: none; white-space: pre-wrap; word-break: break-all; }
  .tl-time { font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 0.75rem; color: var(--muted); min-width: 80px; padding-top: 2px; }
  .tl-label { font-size: 0.9rem; margin-left: 12px; }
  .tl-emoji { font-size: 1.1rem; margin-right: 8px; }
  .empty-state { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--muted); font-size: 0.95rem; }
  .entry-count { font-size: 0.7rem; color: var(--muted); background: var(--border); padding: 1px 6px; border-radius: 8px; margin-left: 4px; }
  #stats { padding: 8px 16px; border-top: 1px solid var(--border); font-size: 0.7rem; color: var(--muted); }
</style>
</head>
<body>
<div id="sidebar">
  <div id="sidebar-header">
    <h1>&#x1f4de; CW Log Viewer</h1>
    <div class="subtitle" id="call-count">Loading...</div>
  </div>
  <div id="filters">
    <input type="text" id="filter-search" placeholder="Search extensions / callers..." oninput="applyFilters()">
  </div>
  <div id="call-list"></div>
  <div id="stats"></div>
</div>
<div id="main">
  <div id="main-header">
    <h2 id="main-title">Select a call from the sidebar</h2>
    <div class="details" id="main-details"></div>
  </div>
  <div id="timeline">
    <div class="empty-state">&#x2190; Select a call to view its timeline</div>
  </div>
</div>
<script>
let calls = [];
let activeCallId = null;

async function loadCalls() {
  var countEl = document.getElementById('call-count');
  var list = document.getElementById('call-list');
  try {
    var resp = await fetch('/api/calls');
    if (!resp.ok) throw new Error('Server returned ' + resp.status);
    calls = await resp.json();
    if (!Array.isArray(calls)) throw new Error('Unexpected response format');
    countEl.textContent = calls.length + ' calls';
    document.getElementById('stats').textContent = calls.length + ' calls loaded';
    renderCallList();
  } catch (err) {
    countEl.textContent = 'Error loading calls';
    list.innerHTML = '<div class="call-item" style="cursor:default;color:var(--accent)">Failed to load calls: ' + (err.message || 'Unknown error') + '</div>';
    console.error('loadCalls error:', err);
  }
}

function renderCallList(filterText) {
  filterText = filterText || '';
  var list = document.getElementById('call-list');
  var ft = filterText.toLowerCase();
  var filtered = calls.filter(function(c) {
    if (!ft) return true;
    return c.caller.toLowerCase().indexOf(ft) !== -1 ||
           c.destination.toLowerCase().indexOf(ft) !== -1 ||
           c.id.toLowerCase().indexOf(ft) !== -1;
  });

  if (filtered.length === 0) {
    list.innerHTML = '<div class="call-item" style="cursor:default;color:var(--muted)">No calls match</div>';
    return;
  }

  var html = '';
  for (var i = 0; i < filtered.length; i++) {
    var c = filtered[i];
    var cls = 'call-item';
    if (c.id === activeCallId) cls += ' active';
    html += '<div class="' + cls + '" data-call-id="' + c.id + '">';
    html += '<div class="cid">' + c.id + ' <span class="entry-count">' + c.entries + ' entries</span></div>';
    html += '<div class="meta"><span>' + (c.date || '') + '</span><span>' + c.start + '</span><span>&#x2192; ' + c.end + '</span>';
    if (c.duration) html += '<span>' + c.duration + 's</span>';
    html += '</div>';
    html += '<div class="meta">' + c.caller + ' &#x2192; ' + c.destination + '</div>';
    html += '</div>';
  }
  list.innerHTML = html;
}

document.getElementById('call-list').addEventListener('click', function(evt) {
  var el = evt.target;
  while (el && el !== this) {
    if (el.classList.contains('call-item') && el.dataset.callId) {
      selectCall(el.dataset.callId);
      return;
    }
    el = el.parentElement;
  }
});

function applyFilters() {
  renderCallList(document.getElementById('filter-search').value);
}

async function selectCall(callId) {
  activeCallId = callId;
  renderCallList(document.getElementById('filter-search').value);

  var resp = await fetch('/api/calls/' + encodeURIComponent(callId));
  var detail = await resp.json();

  document.getElementById('main-title').textContent = detail.id + ' — ' + (detail.date || '');
  document.getElementById('main-details').innerHTML =
    detail.caller + ' &#x2192; ' + detail.destination +
    ' | ' + detail.start + ' &#x2192; ' + detail.end +
    ' | ' + (detail.duration ? detail.duration + 's' : '') +
    ' | ' + detail.entries + ' entries';

  if (!detail.events || detail.events.length === 0) {
    document.getElementById('timeline').innerHTML =
      '<div class="empty-state">No key events extracted</div>';
    return;
  }

  var html = '';
  for (var i = 0; i < detail.events.length; i++) {
    var e = detail.events[i];
    html += '<div class="tl-event clickable" data-event-idx="' + i + '">';
    html += '<div class="tl-time">' + e.time + '</div>';
    var spaceIdx = e.label.indexOf(' ');
    var emojiPart = spaceIdx > 0 ? e.label.slice(0, spaceIdx) : e.label;
    var textPart = spaceIdx > 0 ? e.label.slice(spaceIdx + 1) : '';
    html += '<div class="tl-label"><span class="tl-emoji">' + emojiPart + '</span>' + textPart + '</div>';
    html += '<div class="tl-raw" style="display:none">' + (e.process || '') + ': ' + escHtml(e.raw || '') + '</div>';
    html += '</div>';
  }
  document.getElementById('timeline').innerHTML = html;
}

document.getElementById('timeline').addEventListener('click', function(evt) {
  var el = evt.target;
  while (el && el !== this) {
    if (el.classList.contains('tl-event')) {
      var raw = el.querySelector('.tl-raw');
      if (raw) {
        raw.style.display = raw.style.display === 'none' ? 'block' : 'none';
      }
      return;
    }
    el = el.parentElement;
  }
});

function escHtml(text) {
  return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

loadCalls();
</script>
</body>
</html>
'''


def _call_to_dict(cf: CallFlow, call_id: str) -> dict:
    """Convert a call-flow summary to a JSON-serializable dict."""
    entries = cf.get_call(call_id)
    if not entries:
        return {}
    first = entries[0]
    last = entries[-1]
    duration = (
        (last.timestamp - first.timestamp).total_seconds()
        if (first.timestamp and last.timestamp
            and first.timestamp != datetime.min
            and last.timestamp != datetime.min)
        else 0
    )

    caller_name = 'Unknown'
    for e in entries:
        msg = e.message or ''
        if 'Set Caller name to' in msg:
            m = re.search(r'Set Caller name to "([^"]+)"', msg)
            if m:
                caller_name = m.group(1)
                break

    destination = '?'
    for e in entries:
        if e.action == 'Dial' and e.params:
            dest = cf._first_param(e.params)
            destination = cf._normalize_target(dest) if dest else '?'
            break
        msg = e.message or ''
        if msg.startswith('-- Called '):
            destination = cf._normalize_target(msg.replace('-- Called ', '', 1))
            break

    fmt_ts = (
        (lambda t: t.strftime('%H:%M:%S') if t and t != datetime.min else '--:--:--')
    )
    fmt_date = (
        (lambda t: t.strftime('%b %d') if t and t != datetime.min else '')
    )
    return {
        'id': call_id,
        'date': fmt_date(first.timestamp),
        'start': fmt_ts(first.timestamp),
        'end': fmt_ts(last.timestamp),
        'duration': round(duration),
        'entries': len(entries),
        'caller': caller_name,
        'destination': destination,
    }


def _entry_to_dict(e) -> dict:
    """Convert a LogEntry to a JSON-serializable dict."""
    return {
        'line_number': e.line_number,
        'timestamp': (
            e.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            if e.timestamp and e.timestamp != datetime.min else ''
        ),
        'level': e.level or '',
        'event_id': e.event_id,
        'call_id': e.call_id or '',
        'process': e.process or '',
        'message': (e.message or '')[:200],
        'dialed_number': e.dialed_number or '',
        'context': e.context or '',
        'action': e.action or '',
        'channel': e.channel or '',
    }


class CallFlowHandler(BaseHTTPRequestHandler):
    """HTTP request handler that serves the web UI and REST API."""

    callflow: CallFlow = None  # Set by serve() before starting

    def log_message(self, format, *args):
        """Suppress default stderr logging."""
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_str, status=200):
        body = html_str.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        qs = parse_qs(parsed.query)

        # ── HTML page ──
        if path == '' or path == '/':
            self._send_html(_HTML_PAGE)
            return

        # ── API: list calls ──
        if path == '/api/calls':
            calls = []
            for cid in self.callflow.sorted_call_ids():
                d = _call_to_dict(self.callflow, cid)
                if d:
                    calls.append(d)
            self._send_json(calls)
            return

        # ── API: call detail ──
        if path.startswith('/api/calls/'):
            call_id = path.split('/api/calls/', 1)[1]
            if call_id not in self.callflow.calls:
                self._send_json({'error': 'Call not found'}, 404)
                return
            detail = _call_to_dict(self.callflow, call_id)
            detail['events'] = []
            entries = self.callflow.get_call(call_id)
            for e in entries:
                label = self.callflow._summarize_event(e)
                if not label:
                    continue
                ts = (
                    e.timestamp.strftime('%H:%M:%S')
                    if e.timestamp and e.timestamp != datetime.min
                    else '--:--:--'
                )
                if detail['events'] and detail['events'][-1]['label'] == label:
                    continue
                detail['events'].append({
                    'time': ts,
                    'label': label,
                    'raw': (e.message or '')[:300],
                    'process': e.process or '',
                })
            self._send_json(detail)
            return

        # ── API: entries with optional filters ──
        if path == '/api/entries':
            call_id = qs.get('call_id', [None])[0]
            extension = qs.get('extension', [None])[0]
            process = qs.get('process', [None])[0]
            start_str = qs.get('start', [None])[0]
            end_str = qs.get('end', [None])[0]

            start = None
            end = None
            now = datetime.now()
            if start_str:
                try:
                    h, m = map(int, start_str.split(':'))
                    start = datetime(now.year, 1, 1, h, m, 0)
                except (ValueError, TypeError):
                    pass
            if end_str:
                try:
                    h, m = map(int, end_str.split(':'))
                    end = datetime(now.year, 1, 1, h, m, 0)
                except (ValueError, TypeError):
                    pass

            results = self.callflow.filter_entries(
                call_id=call_id,
                extension=extension,
                process=process,
                start=start,
                end=end,
            )
            self._send_json([_entry_to_dict(e) for e in results[:200]])
            return

        # ── 404 ──
        self._send_json({'error': 'Not found'}, 404)


def serve(cf, host='127.0.0.1', port=8080, open_browser=True):
    """Start the web server.

    Args:
        cf: CallFlow instance with parsed and grouped entries.
        host: Host address to bind to.
        port: Port to listen on.
        open_browser: If True, open the browser automatically.
    """
    CallFlowHandler.callflow = cf
    server = HTTPServer((host, port), CallFlowHandler)
    url = f"http://{host}:{port}"
    print(f"\n  CW Log Viewer")
    print(f"   Web UI: {url}")
    print(f"   Press Ctrl+C to stop.\n")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()