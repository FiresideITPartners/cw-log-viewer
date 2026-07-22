"""CallFlow: groups LogEntry objects by Call-ID for filtering and display."""

from collections import defaultdict
from datetime import datetime
import re
from typing import Optional

from .models import LogEntry

DEFAULT_EXCLUDE_PROCESSES = ['config.c', 'res_awstranscribe.c']


class CallFlow:
    """Groups LogEntry objects by Call-ID with filtering and display methods.

    Entries with a Call-ID are grouped into ``calls`` dict keyed by call_id.
    Entries without a Call-ID (e.g. config.c lines) go into ``noise``.

    ``filter_entries()`` provides a combined filter with noise exclusion
    (config.c and res_awstranscribe.c excluded by default).
    """

    def __init__(self, entries: list[LogEntry]):
        self.entries = entries
        calls: dict[str, list[LogEntry]] = defaultdict(list)
        noise: list[LogEntry] = []

        for e in entries:
            if e.call_id:
                calls[e.call_id].append(e)
            else:
                noise.append(e)

        self.calls: dict[str, list[LogEntry]] = dict(calls)
        self.noise: list[LogEntry] = noise

    def get_call(self, call_id: str) -> list[LogEntry]:
        """Return all entries for a specific Call-ID."""
        return self.calls.get(call_id, [])

    def sorted_call_ids(self) -> list[str]:
        """Return Call-IDs sorted by their hex sequence number."""

        def sort_key(cid: str) -> int:
            try:
                return int(cid.split('-')[1], 16)
            except (IndexError, ValueError):
                return 0

        return sorted(self.calls.keys(), key=sort_key)

    def filter_by_extension(self, ext: str) -> list[LogEntry]:
        """Return entries whose message contains the extension substring."""
        return [e for e in self.entries if ext in (e.message or '')]

    def filter_by_process(self, proc: str) -> list[LogEntry]:
        """Return entries from the exact process name."""
        return [e for e in self.entries if e.process == proc]

    def filter_by_time(
        self,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> list[LogEntry]:
        """Return entries in the inclusive datetime range."""
        results = self.entries
        if start is not None:
            results = [
                e for e in results
                if e.timestamp and e.timestamp != datetime.min and e.timestamp >= start
            ]
        if end is not None:
            results = [
                e for e in results
                if e.timestamp and e.timestamp != datetime.min and e.timestamp <= end
            ]
        return results

    def filter_entries(
        self,
        call_id: Optional[str] = None,
        extension: Optional[str] = None,
        process: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        exclude_processes: Optional[list[str]] = None,
    ) -> list[LogEntry]:
        """Combined filter over all entries.

        Args:
            call_id: Exact match on Call-ID.
            extension: Substring match in the message field.
            process: Exact match on process name.
            start: Inclusive start of time range.
            end: Inclusive end of time range.
            exclude_processes: Processes to exclude.
                Defaults to ``['config.c', 'res_awstranscribe.c']``.
                Pass ``[]`` to keep noise.

        Returns:
            Filtered list of LogEntry objects.
        """
        if exclude_processes is None:
            exclude_processes = DEFAULT_EXCLUDE_PROCESSES

        results = self.entries

        if call_id is not None:
            results = [e for e in results if e.call_id == call_id]
        if extension is not None:
            results = [e for e in results if extension in (e.message or '')]
        if process is not None:
            results = [e for e in results if e.process == process]
        if start is not None or end is not None:
            results = CallFlow(results).filter_by_time(start, end)
        if exclude_processes:
            results = [e for e in results if e.process not in exclude_processes]

        return results

    @staticmethod
    def _quoted_value(text: str, marker: str) -> Optional[str]:
        """Return the first quoted value that follows a marker in text."""
        m = re.search(rf'{re.escape(marker)}\s+"([^"]+)"', text)
        return m.group(1) if m else None

    @staticmethod
    def _first_param(params: str) -> str:
        """Return the first comma-delimited param segment, if any."""
        return (params.split(',')[0] if params else '').strip()

    @staticmethod
    def _normalize_target(target: str) -> str:
        """Normalize a dial target to a readable endpoint identifier."""
        target = target.strip()
        if not target:
            return '?'
        if '/' in target:
            target = target.split('/')[-1]
        if '@' in target:
            target = target.split('@')[0]
        return target or '?'

    def _summarize_event(self, e: LogEntry) -> Optional[str]:
        """Map a log entry to a compact emoji-labeled summary line."""
        msg = e.message or ''
        params = e.params or ''

        # Trunk events
        if 'trunk_calls_count incremented' in msg:
            return '📞 Incoming trunk call started'
        if 'trunk_calls_count decremented' in msg:
            return '📴 Trunk ended'

        # Caller ID
        if 'Set Caller name to' in msg:
            caller = self._quoted_value(msg, 'Set Caller name to')
            if caller:
                return f'👤 Caller: {caller}'
        if 'Set Caller num to' in msg:
            number = self._quoted_value(msg, 'Set Caller num to')
            if number:
                return f'📱 Caller number: {number}'

        # Routing / playback
        if e.action == 'Goto':
            return f'🔀 Route to: {params}'
        if e.action == 'Background':
            sound = self._first_param(params) or params
            if sound:
                return f'🔊 Play menu: {sound}'
        if e.action == 'Playback':
            sound = self._first_param(params) or params
            if sound:
                return f'🔊 Play message: {sound}'

        # Call groups / queues / rings
        if e.action == 'Queue':
            queue_name = self._first_param(params) or '?'
            return f'👥 Call group: {queue_name}'
        if 'CallGroup' in msg:
            group = msg.split('CallGroup,', 1)[1].split(',', 1)[0] if 'CallGroup,' in msg else '?'
            return f'👥 Call group: {group}'
        if 'Called Local/' in msg or 'Called SIP/' in msg:
            m = re.search(r'Called\s+(\S+)', msg)
            target = self._normalize_target(m.group(1)) if m else '?'
            return f'📞 Ring local: {target}'
        if e.action == 'Dial':
            target = self._normalize_target(self._first_param(params) or e.dialed_number or params)
            return f'📞 Dial: {target}'
        if ' is ringing' in msg:
            m = re.search(r'(\S+) is ringing', msg)
            target = m.group(1) if m else '?'
            return f'🔔 Ringing: {target}'
        if 'answered' in msg:
            m = re.search(r'(\S+) answered (\S+)', msg)
            if m:
                return f'✅ Answered: {m.group(1)} ↔ {m.group(2)}'
            return '✅ Answered'
        if 'Nobody picked up' in msg:
            m = re.search(r'in (\d+) ms', msg)
            timeout = m.group(1) if m else '?'
            return f'⏰ Timeout: {timeout} ms'

        # Voicemail / recording / hangup
        if e.action == 'VoiceMail':
            target = params.split('@', 1)[0] if params else '?'
            return f'📬 Voicemail: {target}'
        if 'Recording the message' in msg:
            return '🎙️ Recording voicemail'
        if 'User hung up' in msg:
            return '📴 Caller hung up'

        # DTMF
        if 'DTMF end passthrough' in msg or 'DTMF end ignored' in msg:
            return None
        if 'DTMF end' in msg:
            m = re.search(r"DTMF end '(\S+)'", msg)
            digit = m.group(1) if m else '?'
            return f'🔢 DTMF: {digit}'

        # Outbound / call end / handlers
        if 'TrunkCall,outgoing' in msg:
            return '📤 Outbound trunk call'
        if 'Spawn extension' in msg and 'exited non-zero' in msg:
            m = re.search(r'Spawn extension \(([^,]+),\s*([^,]+),', msg)
            if m:
                return f'🏁 Leg ended: {m.group(1)}/{m.group(2)}'
            return '🏁 Leg ended'
        if 'Gosub(hdlr' in msg:
            return '🔄 Handler routine'

        return None

    def get_keys_for_call(self, call_id: str) -> list[str]:
        """Return human-readable key event descriptions for a call."""
        entries = self.calls.get(call_id, [])
        keys: list[str] = []

        for e in entries:
            label = self._summarize_event(e)
            if not label:
                continue
            ts = (
                e.timestamp.strftime('%H:%M:%S')
                if e.timestamp and e.timestamp != datetime.min
                else '--:--:--'
            )
            line = f'{ts}  {label}'
            if keys and keys[-1] == line:
                continue
            keys.append(line)

        return keys

    def summarize_call(self, call_id: str) -> str:
        """Return a formatted multi-line summary of a call's key events."""
        entries = self.calls.get(call_id, [])
        if not entries:
            return f"Call {call_id}: (no entries)"

        first = entries[0]
        last = entries[-1]
        duration = (
            (last.timestamp - first.timestamp).total_seconds()
            if first.timestamp and last.timestamp
            and first.timestamp != datetime.min
            and last.timestamp != datetime.min
            else 0
        )

        # Find caller name
        caller_name = 'Unknown'
        for e in entries:
            msg = e.message or ''
            if 'Set Caller name to' in msg:
                import re
                m = re.search(r'Set Caller name to "([^"]+)"', msg)
                if m:
                    caller_name = m.group(1)
                    break

        # Find destination
        destination = '?'
        for e in entries:
            if e.action == 'Dial' and e.params:
                destination = self._normalize_target(self._first_param(e.params))
                break
            msg = e.message or ''
            if msg.startswith('-- Called '):
                destination = self._normalize_target(msg.replace('-- Called ', '', 1))
                break

        header = (
            f"\n{'=' * 70}\n"
            f"Call {call_id}  |  "
            f"{first.timestamp.strftime('%H:%M:%S')} "
            f"→ {last.timestamp.strftime('%H:%M:%S')}"
            f"  ({duration:.0f}s)\n"
            f"Caller: {caller_name}  →  Destination: {destination}\n"
            f"{'-' * 70}"
        )

        keys = self.get_keys_for_call(call_id)
        if keys:
            return header + '\n' + '\n'.join(keys) + f"\n{'=' * 70}\n"
        return header + '\n  (no key events extracted)\n'
