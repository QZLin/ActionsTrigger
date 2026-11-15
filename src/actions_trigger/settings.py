"""Runtime settings, read from environment variables.

Values come from the process environment first; a ``.env`` file in the working
directory is loaded as a fallback (see ``.env.example``).  Nothing is validated
at import time, so importing this package never fails because a secret is
missing - the error surfaces when the value is actually needed.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

API_URL_DEFAULT = 'https://api.github.com'
CONFIG_DIR_DEFAULT = 'config'
CONFIG_SOURCE_DEFAULT = 'release'
CONFIG_TAG_DEFAULT = 'store-config'
CONFIG_BRANCH_DEFAULT = 'config'
ENV_FILE_DEFAULT = '.env'

_TRUTHY = {'1', 'true', 'yes', 'on'}
_DEBUG_FILE = '_DEBUG'


class MissingSettingError(RuntimeError):
    """Raised when a required environment variable is not configured."""


def _env_file() -> Path:
    return Path(os.environ.get('ACTIONS_TRIGGER_ENV_FILE', ENV_FILE_DEFAULT))


def load_env() -> bool:
    """Load the ``.env`` file; existing environment variables win."""
    return load_dotenv(_env_file(), override=False)


def _first(*names: str) -> str | None:
    """Return the first non-empty environment variable among ``names``."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _required(names: tuple[str, ...], hint: str) -> str:
    value = _first(*names)
    if value is None:
        raise MissingSettingError(f'{"/".join(names)} is not set ({hint})')
    return value


def repository() -> str:
    """``owner/repo`` holding the unit values; set by Actions as ``GITHUB_REPOSITORY``."""
    return _required(('ACTIONS_TRIGGER_REPO', 'GITHUB_REPOSITORY'), 'see .env.example')


def token() -> str:
    """Token used for the GitHub REST API (surrounding whitespace removed)."""
    return _required(('ACTIONS_TRIGGER_TOKEN', 'GITHUB_TOKEN', 'GH_TOKEN'), 'see .env.example').strip()


def api_url() -> str:
    """Base URL of the REST API (overridable for GitHub Enterprise)."""
    return (_first('ACTIONS_TRIGGER_API_URL', 'GITHUB_API_URL') or API_URL_DEFAULT).rstrip('/')


def config_dir() -> Path:
    """Directory scanned for unit definitions."""
    return Path(_first('ACTIONS_TRIGGER_CONFIG_DIR') or CONFIG_DIR_DEFAULT)


def config_source() -> str:
    """Where :mod:`actions_trigger.external_config` looks for configs: ``release`` or ``branch``."""
    return (_first('ACTIONS_TRIGGER_CONFIG_SOURCE') or CONFIG_SOURCE_DEFAULT).lower()


def config_tag() -> str:
    """Release tag whose assets hold the configs (``source=release``)."""
    return _first('ACTIONS_TRIGGER_CONFIG_TAG') or CONFIG_TAG_DEFAULT


def config_branch() -> str:
    """Branch holding the configs (``source=branch``)."""
    return _first('ACTIONS_TRIGGER_CONFIG_BRANCH') or CONFIG_BRANCH_DEFAULT


def config_path() -> str:
    """Directory of the configs inside the branch; empty means the branch root."""
    return (_first('ACTIONS_TRIGGER_CONFIG_PATH') or '').strip('/')


def debug() -> bool:
    """Verbose logging when ``ACTIONS_TRIGGER_DEBUG`` is truthy or a ``_DEBUG`` file exists."""
    if (_first('ACTIONS_TRIGGER_DEBUG') or '').lower() in _TRUTHY:
        return True
    return Path(_DEBUG_FILE).exists()


def in_actions() -> bool:
    """True when running inside a GitHub Actions job."""
    return (_first('GITHUB_ACTIONS') or '').lower() == 'true'


def run_id() -> int | None:
    """Id of the current workflow run (``GITHUB_RUN_ID``), ``None`` outside Actions."""
    value = _first('GITHUB_RUN_ID')
    return int(value) if value and value.isdigit() else None


def event_name() -> str | None:
    """Event that started the current run (``GITHUB_EVENT_NAME``)."""
    return _first('GITHUB_EVENT_NAME')


def prune_event() -> str | None:
    """Event used to decide whether duplicate runs are pruned.

    ``ACTIONS_TRIGGER_PRUNE_EVENT`` overrides ``GITHUB_EVENT_NAME``, which makes it
    possible to exercise the ``schedule`` path from a manual dispatch.
    """
    return _first('ACTIONS_TRIGGER_PRUNE_EVENT') or event_name()


load_env()
