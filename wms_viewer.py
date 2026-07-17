#!/usr/bin/env python3
"""Wildix Call Weaver Log Viewer — parse, filter, and visualize call-flow logs."""

import argparse
import sys
from datetime import datetime


def parse_time(time_str: str) -> datetime:
    """Parse a time string like '12:38' or '12:38:00' into a datetime.

    Uses a fixed reference date (2026-07-16) since log timestamps are
    month-day-hour:minute:second without a year.  The actual date is
    irrelevant for time-of-day comparisons; only the time component
    matters for filtering.
    """
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            t = datetime.strptime(time_str, fmt)
            return datetime(2026, 7, 16, t.hour, t.minute, t.second)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid time: '{time_str}'.  Expected HH:MM or HH:MM:SS."
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for wms_viewer."""

    parser = argparse.ArgumentParser(
        prog='wms_viewer',
        description='Parse and filter Wildix Call Weaver log files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n'
               '  wms_viewer cwtrunc.txt                           '
               '# all entries (noise excluded)\n'
               '  wms_viewer cwtrunc.txt --call-id C-0000004c       '
               '# one call\n'
               '  wms_viewer cwtrunc.txt --summary                  '
               '# call-flow summaries for all calls\n'
               '  wms_viewer cwtrunc.txt --summary -c C-0000004c    '
               '# summary for one call\n'
               '  wms_viewer cwtrunc.txt --ext 102                  '
               '# filter by extension\n'
               '  wms_viewer cwtrunc.txt -p app_dial.c              '
               '# filter by process\n'
               '  wms_viewer cwtrunc.txt --from 12:38 --to 12:40    '
               '# time range',
    )

    # ── positional ─────────────────────────────────────────────────
    parser.add_argument(
        'logfile',
        help='Path to the Call Weaver log file to parse.',
    )

    # ── filtering ──────────────────────────────────────────────────
    parser.add_argument(
        '--call-id', '-c',
        metavar='ID',
        help='Filter by exact Call-ID (e.g. C-0000004a).',
    )

    parser.add_argument(
        '--extension', '--ext', '-e',
        metavar='NUMBER',
        help='Filter lines whose message contains this extension substring.',
    )

    parser.add_argument(
        '--process', '-p',
        metavar='NAME',
        help='Filter by process name (e.g. pbx_lua.c, app_dial.c).',
    )

    # ── time range ─────────────────────────────────────────────────
    parser.add_argument(
        '--from', '-f',
        dest='time_from',
        type=parse_time,
        metavar='TIME',
        help='Start time — HH:MM or HH:MM:SS (inclusive).',
    )

    parser.add_argument(
        '--to', '-t',
        dest='time_to',
        type=parse_time,
        metavar='TIME',
        help='End time — HH:MM or HH:MM:SS (inclusive).',
    )

    # ── output modes ───────────────────────────────────────────────
    parser.add_argument(
        '--summary', '-s',
        action='store_true',
        help='Show call-flow summaries instead of raw log entries.',
    )

    parser.add_argument(
        '--list-calls', '-l',
        action='store_true',
        help='Print a table of all Call-IDs with their start/end times.',
    )

    # ── noise control ──────────────────────────────────────────────
    parser.add_argument(
        '--show-noise',
        action='store_true',
        help='Include config.c and res_awstranscribe.c noise lines '
             '(excluded by default).',
    )

    # ── timestamp year ─────────────────────────────────────────────
    parser.add_argument(
        '--year',
        type=int,
        default=2026,
        metavar='YYYY',
        help='Calendar year used when interpreting month-day timestamps '
             '(default: %(default)s).',
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate handler.

    Imports of the wms_viewer library modules are deferred until after
    argument parsing so that ``--help`` works without those modules
    being installed.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Deferred imports — only needed when actually running, not for --help.
    from src.wms_viewer.parser import LogParser   # noqa: E402
    from src.wms_viewer.callflow import CallFlow  # noqa: E402

    # Load and parse
    log_parser = LogParser(year=args.year)
    entries = log_parser.parse_file(args.logfile)
    cf = CallFlow(entries)

    if args.list_calls:
        _print_call_list(cf)
        return

    # Filter
    exclude = None if args.show_noise else ['config.c', 'res_awstranscribe.c']
    results = cf.filter_entries(
        call_id=args.call_id,
        extension=args.extension,
        process=args.process,
        start=args.time_from,
        end=args.time_to,
        exclude_processes=exclude,
    )

    if args.summary:
        _print_summaries(cf, args)
    else:
        _print_raw(results)


def _print_call_list(cf: 'CallFlow') -> None:
    """Print a tabular listing of all Call-IDs."""
    header = f"{'Call-ID':<16} {'Start':>8} {'End':>8} {'Entries':>8}  First Message"
    print(header)
    print('-' * len(header))
    for cid in cf.sorted_call_ids():
        call = cf.get_call(cid)
        start = call[0].timestamp.strftime('%H:%M:%S')
        end = call[-1].timestamp.strftime('%H:%M:%S')
        first_msg = call[0].message[:60]
        print(f'{cid:<16} {start:>8} {end:>8} {len(call):>8}  {first_msg}')


def _print_summaries(cf: 'CallFlow', args: argparse.Namespace) -> None:
    """Print call-flow summaries for one or all calls."""
    call_ids = [args.call_id] if args.call_id else cf.sorted_call_ids()
    for cid in call_ids:
        if cid not in cf.calls:
            continue
        call_entries = cf.get_call(cid)
        if args.time_from and all(e.timestamp < args.time_from
                                  for e in call_entries):
            continue
        if args.time_to and all(e.timestamp > args.time_to
                                for e in call_entries):
            continue
        print(cf.summarize_call(cid))
        print()


def _print_raw(results: list) -> None:
    """Print a filtered table of raw log entries."""
    header = (f"{'Time':>8} {'Level':<8} {'Call-ID':<14}"
              f" {'Process':<25} Message")
    print(header)
    print('-' * len(header))
    for e in results:
        ts = e.timestamp.strftime('%H:%M:%S')
        cid = e.call_id or '-'
        msg = e.message[:80]
        print(f'{ts:>8} {e.level:<8} {cid:<14} {e.process:<25} {msg}')
    print(f'\n--- {len(results)} entries shown ---')


if __name__ == '__main__':
    main()