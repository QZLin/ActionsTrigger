"""Clean historical duplicate scheduled workflow runs on demand.

Unlike the live pruner, historical runs do not have a state hash recorded by the
old version of the workflow. This command therefore uses run annotations:

* a successful scheduled run with at least one ``executed N/M action(s)``
  annotation is a change boundary and is never deleted;
* a successful scheduled run whose units all report ``skipped`` is unchanged;
* within each consecutive unchanged segment, the earliest and latest runs are
  kept and runs between them are deleted.

The command is dry-run by default. Pass ``--delete`` to perform deletions.
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from . import settings
from .rest_api import ActionsCmd, ApiError, _next_page, api_headers, delete_workflow_run

_EXECUTED_RE = re.compile(r'^#[^ ]+ executed \d+/\d+ action\(s\)$')
_SKIPPED_RE = re.compile(r'^#[^ ]+ skipped$')


@dataclass(frozen=True)
class WorkflowRun:
    id: int
    created_at: str
    status: str
    conclusion: str | None
    event: str


@dataclass(frozen=True)
class RunClassification:
    run: WorkflowRun
    changed: bool
    unit_annotations: tuple[str, ...]


def _get(url: str, **kwargs: Any) -> requests.Response:
    return requests.get(url, headers=api_headers(), timeout=30, **kwargs)


def list_scheduled_runs(repo: str, workflow: str = 'main.yml',
                        *, per_page: int = 100) -> list[WorkflowRun]:
    """Return completed schedule runs, oldest first, following API pagination."""
    url: str | None = f'{settings.api_url()}/repos/{repo}/actions/workflows/{workflow}/runs'
    params: dict[str, Any] | None = {'event': 'schedule', 'per_page': per_page}
    result: list[WorkflowRun] = []
    while url:
        response = _get(url, params=params)
        if response.status_code != 200:
            raise ApiError(f'list scheduled runs of {repo}', response)
        for item in response.json().get('workflow_runs', []):
            if item.get('status') != 'completed':
                continue
            result.append(WorkflowRun(
                id=int(item['id']),
                created_at=item.get('created_at', ''),
                status=item.get('status', ''),
                conclusion=item.get('conclusion'),
                event=item.get('event', ''),
            ))
        url = _next_page(response)
        params = None
    return sorted(result, key=lambda item: (item.created_at, item.id))


def run_annotations(repo: str, run_id: int) -> list[str]:
    """Return all annotation messages for all jobs of one workflow run."""
    jobs_response = _get(f'{settings.api_url()}/repos/{repo}/actions/runs/{run_id}/jobs')
    if jobs_response.status_code != 200:
        raise ApiError(f'list jobs of run {run_id}', jobs_response)

    messages: list[str] = []
    for job in jobs_response.json().get('jobs', []):
        response = _get(f'{settings.api_url()}/repos/{repo}/check-runs/{job["id"]}/annotations')
        if response.status_code != 200:
            raise ApiError(f'list annotations of job {job["id"]}', response)
        messages.extend(item.get('message', '') for item in response.json())
    return messages


def classify_run(repo: str, run: WorkflowRun) -> RunClassification:
    """Classify a successful completed scheduled run from its unit annotations."""
    if run.conclusion != 'success':
        return RunClassification(run=run, changed=False, unit_annotations=())
    messages = run_annotations(repo, run.id)
    units = tuple(message for message in messages
                  if _EXECUTED_RE.match(message) or _SKIPPED_RE.match(message))
    executed = tuple(message for message in units if _EXECUTED_RE.match(message))
    # No unit annotations means the run cannot be safely classified.
    return RunClassification(run=run, changed=bool(executed), unit_annotations=units)


def unchanged_segments(classified: list[RunClassification]) -> list[list[WorkflowRun]]:
    """Group consecutive confidently-classified unchanged runs."""
    segments: list[list[WorkflowRun]] = []
    current: list[WorkflowRun] = []
    for item in classified:
        if not item.unit_annotations or item.changed:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(item.run)
    if current:
        segments.append(current)
    return segments


def candidate_runs(classified: list[RunClassification]) -> list[WorkflowRun]:
    """Return the middle runs of every unchanged segment."""
    return [run for segment in unchanged_segments(classified) for run in segment[1:-1]]


@dataclass
class CleanupResult:
    scanned: int
    classified: int
    candidates: list[WorkflowRun]
    deleted: list[int]
    dry_run: bool

    @property
    def kept(self) -> int:
        return self.classified - len(self.candidates)


def cleanup(repo: str, workflow: str = 'main.yml', *, delete: bool = False,
            before: str | None = None) -> CleanupResult:
    """Scan history and optionally delete duplicate middle runs."""
    runs = list_scheduled_runs(repo, workflow)
    if before:
        cutoff = datetime.fromisoformat(before.replace('Z', '+00:00'))
        runs = [run for run in runs if datetime.fromisoformat(run.created_at.replace('Z', '+00:00')) < cutoff]

    classified = [classify_run(repo, run) for run in runs]
    candidates = candidate_runs(classified)
    deleted: list[int] = []
    for run in candidates:
        if not delete:
            continue
        if delete_workflow_run(repo, run.id):
            deleted.append(run.id)
    return CleanupResult(len(runs), len([item for item in classified if item.unit_annotations]),
                         candidates, deleted, not delete)


def describe(result: CleanupResult) -> str:
    mode = 'dry-run' if result.dry_run else 'delete'
    ids = ', '.join(f'#{run.id}' for run in result.candidates) or 'none'
    deleted = ', '.join(f'#{run_id}' for run_id in result.deleted) or 'none'
    return (f'historical duplicate cleanup ({mode}): scanned={result.scanned}, '
            f'classified={result.classified}, candidates={ids}, deleted={deleted}')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workflow', default='main.yml', help='workflow file or id (default: main.yml)')
    parser.add_argument('--before', help='only inspect runs before an ISO-8601 timestamp')
    parser.add_argument('--delete', action='store_true', help='actually delete candidates; default is dry-run')
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s',
                        datefmt='%H:%M:%S', level=logging.INFO)
    args = build_parser().parse_args(argv)
    try:
        result = cleanup(settings.repository(), args.workflow, delete=args.delete, before=args.before)
    except (settings.MissingSettingError, ApiError) as error:
        logging.error(error)
        ActionsCmd.error(str(error))
        return 1
    message = describe(result)
    logging.info(message)
    ActionsCmd.notice(message)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
