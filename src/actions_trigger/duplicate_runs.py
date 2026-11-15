"""Delete older duplicates of scheduled runs by hashing the key information.

The *key information* of a run is the state of every unit, i.e. the upstream
fingerprints the conditions observed (``last_commit_sha``, ``last_tag``,
``last_hash``, ...).  It is hashed after the run and compared with the hash the
same run observed before it started:

* hashes differ - the run discovered something new; it is kept and only booked as
  the earliest run of that state
* hashes match - the run learned nothing, so it is a duplicate of every other run
  that observed the same hash

For each distinct hash one window is kept, holding the earliest booked run and the
latest duplicate; a duplicate in between is deleted through the REST API.  Runs
that changed the key information are never deleted, and runs of other events
(push, manual) are ignored.  Nothing is guessed about history that was never
booked, so no pre-existing run is ever touched.

The windows live in one repository Actions variable written by the runs
themselves: ``ACTIONS_TRIGGER_DUP_STATE``, for example
``{"<hash>": [earliest_run, latest_duplicate_run], ...}``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping

from . import settings
from .rest_api import (ActionsCmd, ApiError, create_value, delete_workflow_run, repo_values,
                       update_values)

DUP_VAR = 'ACTIONS_TRIGGER_DUP_STATE'
SCHEDULE_EVENT = 'schedule'
MAX_WINDOWS = 20


def fingerprint(states: Mapping[str, Any]) -> str:
    """Hash the key information, independent of dict ordering."""
    payload = json.dumps(states, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass
class PruneResult:
    """What :func:`prune` did, phrased for a log line or an annotation."""

    action: str  # skipped | kept | recorded-first | recorded | deleted
    reason: str = ''
    run_id: int | None = None
    hash: str = ''
    first: int | None = None
    last: int | None = None
    deleted: int | None = None

    @property
    def short_hash(self) -> str:
        return self.hash[:12]

    def describe(self) -> str:
        if self.action == 'skipped':
            return f'duplicate run pruning skipped: {self.reason}'
        if self.action == 'kept':
            return f'run #{self.run_id} kept: {self.reason} (state {self.short_hash})'
        if self.action == 'recorded-first':
            return f'run #{self.run_id} kept as the earliest run of state {self.short_hash}'
        if self.action == 'recorded':
            return (f'run #{self.run_id} kept as the latest run of state {self.short_hash}, '
                    f'earliest is #{self.first}')
        dropped = f'#{self.deleted}' if self.deleted is not None else 'previous duplicate (not deleted)'
        return (f'run #{self.run_id} kept as the latest run of state {self.short_hash}, '
                f'removed {dropped}; earliest #{self.first} is kept')


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_windows() -> dict[str, list[int | None]]:
    """Read the per-state windows; a missing or broken variable means "nothing booked"."""
    values = {x['name']: x['value'] for x in repo_values(settings.repository())}
    raw = values.get(DUP_VAR)
    if raw is None or raw == 'null':
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logging.warning(f'{DUP_VAR} is not valid json, starting empty')
        return {}
    if not isinstance(data, dict):
        return {}

    windows: dict[str, list[int | None]] = {}
    for state_hash, window in data.items():
        if not isinstance(window, (list, tuple)) or not window:
            continue
        first = _as_int(window[0])
        if first is None:
            continue
        last = _as_int(window[1]) if len(window) > 1 else first
        windows[str(state_hash)] = [first, last]
    return windows


def save_windows(windows: dict[str, list[int | None]]) -> None:
    """Persist the windows, keeping the ``MAX_WINDOWS`` most recently touched ones."""
    while len(windows) > MAX_WINDOWS:
        windows.pop(next(iter(windows)))
    names = {x['name'] for x in repo_values(settings.repository())}
    if DUP_VAR not in names:
        create_value(DUP_VAR)  # created with a 'null' placeholder
    update_values(DUP_VAR, json.dumps(windows, sort_keys=False))


def _touch(windows: dict[str, list[int | None]], state_hash: str,
           first: int, last: int | None) -> None:
    """Store a window and mark it as the most recently used one."""
    windows.pop(state_hash, None)
    windows[state_hash] = [first, last]


def prune(state_hash: str, previous_hash: str, *, run_id: int | None = None,
          event: str | None = None, dry_run: bool = False) -> PruneResult:
    """Prune the duplicates of a finished run.

    ``state_hash`` and ``previous_hash`` hash the key information after and before
    the run; equal hashes mean the run is a duplicate.
    """
    run_id = settings.run_id() if run_id is None else run_id
    event = settings.prune_event() if event is None else event

    if event != SCHEDULE_EVENT:
        return PruneResult('skipped', reason=f'event is {event or "unknown"}, not {SCHEDULE_EVENT}',
                           run_id=run_id, hash=state_hash)
    if run_id is None:
        return PruneResult('skipped', reason='GITHUB_RUN_ID is not set', run_id=run_id,
                           hash=state_hash)

    windows = load_windows()
    window = windows.get(state_hash)
    first = window[0] if window else run_id
    last = window[1] if window else None

    if state_hash != previous_hash:
        # this run discovered the state: keep it and never let it be deleted
        if not dry_run:
            _touch(windows, state_hash, first, last)
            save_windows(windows)
        return PruneResult('kept', reason='key information changed', run_id=run_id,
                           hash=state_hash, first=first, last=last)

    if window is None:
        if not dry_run:
            _touch(windows, state_hash, run_id, run_id)
            save_windows(windows)
        return PruneResult('recorded-first', run_id=run_id, hash=state_hash,
                           first=run_id, last=run_id)

    if last is None or last == first:
        # the earliest run is also the latest one, so nothing can be dropped
        if not dry_run:
            _touch(windows, state_hash, first, run_id)
            save_windows(windows)
        return PruneResult('recorded', run_id=run_id, hash=state_hash, first=first, last=run_id)

    deleted = None
    if not dry_run:
        if delete_workflow_run(settings.repository(), last):
            deleted = last
        _touch(windows, state_hash, first, run_id)
        save_windows(windows)
    return PruneResult('deleted', run_id=run_id, hash=state_hash, first=first, last=run_id,
                       deleted=deleted)


def booked_hash() -> str | None:
    """Hash of the window that is currently open, if any."""
    windows = load_windows()
    if not windows:
        return None
    # the most recently touched window is the one that is still being filled
    return next(reversed(windows))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='actions_trigger-prune',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--status', action='store_true',
                        help='only print the booked windows')
    parser.add_argument('--hash', default=None,
                        help='key-information hash of this run (default: the booked one, '
                             'i.e. "nothing changed since")')
    parser.add_argument('--previous-hash', default=None,
                        help='hash this run observed before it started (default: --hash)')
    parser.add_argument('--run-id', type=int, default=None,
                        help='run id to act on (default: GITHUB_RUN_ID)')
    parser.add_argument('--event', default=None,
                        help='event of this run (default: GITHUB_EVENT_NAME)')
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would happen without deleting or writing anything')
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s',
                        datefmt='%H:%M:%S', level=logging.INFO)
    args = build_parser().parse_args(argv)

    try:
        if args.status:
            windows = load_windows()
            message = 'no window booked yet' if not windows else '; '.join(
                f'{state_hash[:12]} earliest=#{window[0]} latest=#{window[1]}'
                for state_hash, window in windows.items())
            print(message)
            ActionsCmd.notice(f'duplicate windows: {message}')
            return 0

        state_hash = args.hash or booked_hash()
        if state_hash is None:
            logging.error('no window booked yet, pass --hash <hash> [--previous-hash <hash>]')
            return 2
        previous_hash = state_hash if args.previous_hash is None else args.previous_hash
        result = prune(state_hash, previous_hash, run_id=args.run_id, event=args.event,
                       dry_run=args.dry_run)
    except ApiError as e:
        logging.error(e)
        return 1
    logging.info(result.describe())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
