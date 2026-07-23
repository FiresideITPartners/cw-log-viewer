"""Ad-hoc verification: web_ui error handling, API endpoints, raw events.

Write → run → delete.  Not part of the test suite — just confirms the
edit in this turn didn't break anything.
"""

import json
import threading
import urllib.request
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from wms_viewer.web_ui import CallFlowHandler
from wms_viewer.parser import LogParser
from wms_viewer.callflow import CallFlow
import socketserver


def main() -> int:
    parser = LogParser(year=2026)
    entries = parser.parse_file(str(Path(__file__).parent / 'cwtrunc.txt'))
    cf = CallFlow(entries)

    class H(CallFlowHandler):
        pass
    H.callflow = cf

    with socketserver.TCPServer(('127.0.0.1', 0), H) as d:
        port = d.server_address[1]
        t = threading.Thread(target=d.serve_forever, daemon=True)
        t.start()

        # 1. HTML page has error handling
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/') as r:
            html = r.read().decode('utf-8')

        checks = {
            'try/catch in loadCalls': 'try {' in html and '} catch (err)' in html,
            'error message text': 'Failed to load calls' in html,
            'resp.ok check': 'resp.ok' in html,
            'Array.isArray guard': 'Array.isArray' in html,
            'toggleRaw function': 'toggleRaw' in html,
            'tl-raw CSS class': 'tl-raw' in html,
            'escHtml helper': 'escHtml' in html,
        }
        failures = [k for k, v in checks.items() if not v]
        if failures:
            print(f'FAIL HTML: {failures}')
            return 1
        print('HTML error handling + expand: PASS')

        # 2. /api/calls
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/calls') as r:
            calls = json.loads(r.read())
        assert len(calls) == 9, f'Expected 9 calls, got {len(calls)}'
        print('/api/calls: PASS')

        # 3. /api/calls/<id> events have raw+process
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/calls/C-0000004c') as r:
            call = json.loads(r.read())
        for e in call['events']:
            assert 'raw' in e, f'missing raw: {e}'
            assert 'process' in e, f'missing process: {e}'
        print(f'/api/calls/<id> ({len(call["events"])} events with raw+process): PASS')

        d.shutdown()

    print('ALL VERIFIED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())