"""Entry point: execute every unit declared in the config directory.

A unit is a ``type`` plus the arguments of a condition and an action, both of
which name a module in :mod:`actionstrigger.script`.
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import yaml

from . import settings
from .rest_api import ActionsCmd, ResultData, create_value, get_actions_value, update_values

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
    """Import ``actionstrigger.script.<name>``."""
    return importlib.import_module(f'.script.{name}', __package__)


def simple_handler(unit_id: str, args: dict) -> None:
    origin_unit_data = get_unit_data(unit_id)
    unit_data = origin_unit_data.copy()

    cond_result: ResultData = load_handler(args['condition']['name']).handle(args['condition'], unit_data)

    if cond_result.ok:
        act_result: ResultData = load_handler(args['action']['name']).handle(args['action'], unit_data)
        if act_result.ok:
            unit_data.update(act_result.unit_data)
        ActionsCmd.notice(f'#{unit_id} executed')
    else:
        ActionsCmd.notice(f'#{unit_id} skipped')

    if origin_unit_data != unit_data:
        new_value = json.dumps(unit_data)
        logging.info(new_value)
        update_values(unit_id, new_value)
    else:
        logging.debug('unit data unchanged')


HANDLERS: dict[str, Callable[[str, dict], None]] = {
    'simple': simple_handler,
}


def run(config_path: Path | None = None) -> int:
    """Process every config file in ``config_path``; returns a process exit code."""
    config_path = settings.config_dir() if config_path is None else config_path
    if not config_path.is_dir():
        logging.error(f'config directory not found: {config_path}')
        return 1

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
            handler(unit_id, args)

    return 0


def setup_logging() -> None:
    logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s', datefmt='%H:%M:%S')
    logging.getLogger().setLevel(logging.DEBUG if settings.debug() else logging.INFO)


def main() -> int:
    setup_logging()
    try:
        return run()
    except settings.MissingSettingError as e:
        logging.error(e)
        return 2
