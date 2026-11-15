"""Entry point: execute every unit declared in the config directory.

A unit is a ``type`` plus the arguments of a condition and of the actions, both
of which name a module in :mod:`actions_trigger.script`.  ``actions`` is a list
where every item is an action of its own; a single ``action`` is still accepted.
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import yaml

from . import duplicate_runs, settings
from .rest_api import (ActionsCmd, ApiError, ResultData, create_value, get_actions_value,
                       update_values)

try:  # the libyaml based loader is much faster when available
    from yaml import CLoader as Loader
except ImportError:  # pragma: no cover - pure python fallback
    from yaml import Loader


def get_unit_data(unit_id: str, actions_values: list[dict[str, Any]] | None = None) -> dict:
    """Load the stored state of a unit, creating an empty one when absent."""
    if actions_values is None:
        actions_values = get_actions_value()
    found = [x for x in actions_values if x['name'] == unit_id]
    if len(found) == 1:
        content = found[0]['value']
        return json.loads(content) if content != 'null' else {}
    create_value(unit_id)
    return {}


def load_handler(name: str) -> ModuleType:
    """Import ``actions_trigger.script.<name>``."""
    return importlib.import_module(f'.script.{name}', __package__)


def unit_actions(unit_id: str, args: dict) -> list[dict]:
    """Actions of a unit: the ``actions`` list, or the legacy single ``action``."""
    if 'actions' in args:
        actions = args['actions']
        if 'action' in args:
            ActionsCmd.warning(f'#{unit_id} defines both action and actions, ignoring action')
    elif 'action' in args:
        actions = [args['action']]
    else:
        ActionsCmd.error(f'#{unit_id} defines neither action nor actions')
        return []

    if isinstance(actions, dict):  # tolerate a single mapping
        ActionsCmd.warning(f'#{unit_id} actions should be a list, got a mapping')
        actions = [actions]
    elif actions is None:  # `actions:` without a value
        actions = []
    elif not isinstance(actions, list):
        ActionsCmd.error(f'#{unit_id} actions must be a list')
        return []

    valid = []
    for i, action in enumerate(actions):
        if not isinstance(action, dict) or 'name' not in action:
            ActionsCmd.error(f'#{unit_id} actions[{i}] must be a mapping with a name')
            continue
        valid.append(action)
    return valid


def simple_handler(unit_id: str, args: dict) -> 'UnitOutcome | None':
    """Run one unit; returns the state it observed before and after."""
    actions = unit_actions(unit_id, args)
    if not actions:
        logging.error(f'#{unit_id}: no action to run')
        return None

    origin_unit_data = get_unit_data(unit_id)
    unit_data = origin_unit_data.copy()

    cond_result: ResultData = load_handler(args['condition']['name']).handle(args['condition'], unit_data)

    if cond_result.ok:
        executed = 0
        for action in actions:
            act_result: ResultData = load_handler(action['name']).handle(action, unit_data)
            if act_result.ok:
                unit_data.update(act_result.unit_data)
                executed += 1
            else:
                ActionsCmd.warning(f'#{unit_id} action {action["name"]} failed')
        ActionsCmd.notice(f'#{unit_id} executed {executed}/{len(actions)} action(s)')
    else:
        ActionsCmd.notice(f'#{unit_id} skipped')

    if origin_unit_data != unit_data:
        new_value = json.dumps(unit_data)
        logging.info(new_value)
        update_values(unit_id, new_value)
    else:
        logging.debug('unit data unchanged')

    return UnitOutcome(origin=origin_unit_data, final=unit_data, executed=cond_result.ok)


HANDLERS: dict[str, Callable[[str, dict], 'UnitOutcome | None']] = {
    'simple': simple_handler,
}


@dataclass
class UnitOutcome:
    """State of one unit around a run."""

    origin: dict
    final: dict
    executed: bool

    @property
    def changed(self) -> bool:
        return self.origin != self.final


@dataclass
class RunReport:
    """Outcome of one pass over the config directory."""

    config_path: Path
    outcomes: dict[str, UnitOutcome] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    exit_code: int = 0

    @property
    def states(self) -> dict[str, dict]:
        """Key information of the run: the state of every unit afterwards."""
        return {unit_id: outcome.final for unit_id, outcome in self.outcomes.items()}

    @property
    def origin_states(self) -> dict[str, dict]:
        """Key information as it was known when the run started."""
        return {unit_id: outcome.origin for unit_id, outcome in self.outcomes.items()}

    @property
    def fingerprint(self) -> str:
        return duplicate_runs.fingerprint(self.states)

    @property
    def origin_fingerprint(self) -> str:
        return duplicate_runs.fingerprint(self.origin_states)

    @property
    def executed(self) -> list[str]:
        """Units whose condition detected an upstream change."""
        return [unit_id for unit_id, outcome in self.outcomes.items() if outcome.executed]

    @property
    def changed(self) -> bool:
        return self.fingerprint != self.origin_fingerprint


def run(config_path: Path | None = None) -> RunReport:
    """Process every config file in ``config_path``."""
    config_path = settings.config_dir() if config_path is None else config_path
    report = RunReport(config_path)
    if not config_path.is_dir():
        logging.error(f'config directory not found: {config_path}')
        report.exit_code = 1
        return report

    for conf_path in sorted(p for p in config_path.iterdir() if p.is_file()):
        logging.info(str(conf_path))
        ActionsCmd.notice(str(conf_path))
        with conf_path.open(encoding='utf-8') as f:
            data = yaml.load(f, Loader)
        if data is None:
            ActionsCmd.warning('Empty conf')
            continue

        for unit_id, args in data.items():
            unit_id = unit_id.upper()
            if 'type' not in args:
                ActionsCmd.error(f'{unit_id}: key type must exist')
                continue

            unit_type = args['type']
            ActionsCmd.info(f'{unit_id}#{unit_type}')

            handler = HANDLERS.get(unit_type)
            if handler is None:
                ActionsCmd.error(f'Unimplemented handler {unit_type}')
                continue
            try:
                outcome = handler(unit_id, args)
            except Exception as e:  # one broken unit must not stop the others
                logging.exception(f'#{unit_id} failed')
                ActionsCmd.error(f'#{unit_id} failed: {type(e).__name__}: {e}')
                report.failed[unit_id] = f'{type(e).__name__}: {e}'
                continue
            if outcome is not None:
                report.outcomes[unit_id] = outcome

    return report


def setup_logging() -> None:
    logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s', datefmt='%H:%M:%S')
    logging.getLogger().setLevel(logging.DEBUG if settings.debug() else logging.INFO)


def prune_duplicate_runs(report: RunReport) -> None:
    """Drop older duplicates of an unchanged scheduled run; never breaks the run."""
    if report.exit_code != 0:
        return
    try:
        result = duplicate_runs.prune(report.fingerprint, report.origin_fingerprint)
    except settings.MissingSettingError as e:
        logging.debug(f'duplicate run pruning needs GitHub settings: {e}')
        return
    except Exception as e:  # pruning is a janitor job, it must not fail the run
        logging.error(f'duplicate run pruning failed: {e}')
        return

    logging.info(result.describe())
    if result.action != 'skipped':
        ActionsCmd.notice(result.describe())


def main() -> int:
    setup_logging()
    try:
        report = run()
    except settings.MissingSettingError as e:
        logging.error(e)
        return 2
    except ApiError as e:
        logging.error(e)
        return 1

    if report.changed:
        logging.info(f'key information changed, observed by {", ".join(report.executed) or "no unit"}')
    else:
        logging.info(f'key information unchanged (state {report.fingerprint[:12]})')
    # a unit failure leaves the key information incomplete, so nothing is pruned
    if report.failed:
        ActionsCmd.error(f'{len(report.failed)} unit(s) failed: {", ".join(report.failed)}')
        return 1

    prune_duplicate_runs(report)
    return report.exit_code
