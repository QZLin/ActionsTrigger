"""Download the yaml unit configs from an external location.

Two sources are supported:

``release`` (default)
    Assets of a release tagged ``store-config``; only ``*.yaml`` / ``*.yml``
    assets are used.
``branch``
    ``*.yaml`` / ``*.yml`` files of a directory in a branch - by default the
    root of the branch named ``config``.

Files are written into the config directory (``ACTIONS_TRIGGER_CONFIG_DIR``,
default ``config``).  Existing files are kept unless ``--allow-override`` is
given, so a local config always wins over the published one.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import requests

from . import settings
from .rest_api import get_release_by_tag, list_contents

SOURCES = ('release', 'branch')
YAML_SUFFIXES = frozenset({'.yaml', '.yml'})


@dataclass(frozen=True)
class ConfigFile:
    """A remote yaml config waiting to be downloaded."""

    name: str
    url: str


def is_yaml(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in YAML_SUFFIXES


def from_release(repo: str, tag: str) -> list[ConfigFile]:
    """Configs attached to the release ``tag`` of ``repo``."""
    release = get_release_by_tag(repo, tag)
    if release is None:
        logging.info(f'no available online config in release {repo}#{tag}')
        return []
    files = [ConfigFile(asset['name'], asset['browser_download_url'])
             for asset in release.get('assets', [])
             if is_yaml(asset['name'])]
    if not files:
        logging.info(f'empty online config in release {repo}#{tag}')
    return files


def from_branch(repo: str, branch: str, path: str = '') -> list[ConfigFile]:
    """Configs stored in the directory ``path`` of ``branch`` of ``repo``."""
    entries = list_contents(repo, path, ref=branch) or []
    files = []
    for entry in entries:
        if entry.get('type') != 'file' or not entry.get('download_url'):
            logging.debug(f'skip non downloadable entry {entry.get("path")}')
            continue
        if not is_yaml(entry['name']):
            logging.debug(f'skip non yaml file {entry.get("path")}')
            continue
        files.append(ConfigFile(entry['name'], entry['download_url']))
    if not files:
        logging.info(f'no yaml config found in branch {repo}#{branch}:{path or "/"}')
    return files


def download(url: str, target: Path) -> None:
    r = requests.get(url)
    with target.open('wb') as f:
        f.write(r.content)
    logging.info(f'write to {target}')


def _safe_target(target_dir: Path, name: str) -> Path | None:
    """Reject names that would escape ``target_dir``."""
    if not name or PurePosixPath(name).name != name or name in {'.', '..'}:
        logging.warning(f'skip unsafe config name {name!r}')
        return None
    return target_dir / name


def sync_configs(repo: str, source: str, *, tag: str | None = None, branch: str | None = None,
                 path: str | None = None, allow_override: bool = False) -> list[Path]:
    """Copy the configs of ``source`` into the config directory; returns the written paths."""
    if source not in SOURCES:
        raise ValueError(f'unknown source {source!r}, expected one of {SOURCES}')

    if source == 'release':
        files = from_release(repo, settings.config_tag() if tag is None else tag)
    else:
        files = from_branch(repo,
                            settings.config_branch() if branch is None else branch,
                            settings.config_path() if path is None else path)
    logging.info([x.name for x in files])

    target_dir = settings.config_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for x in files:
        target = _safe_target(target_dir, x.name)
        if target is None:
            continue
        if not allow_override and target.exists():
            logging.warning(f'skip {target} because file existed and override is not allowed')
            continue
        download(x.url, target)
        written.append(target)
    logging.info(f'{len(written)} config(s) downloaded into {target_dir}')
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='actions_trigger-ext-config',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('repo', nargs='?', default=None,
                        help='repository holding the configs (default: ACTIONS_TRIGGER_REPO / GITHUB_REPOSITORY)')
    parser.add_argument('-s', '--source', choices=SOURCES, default=settings.config_source(),
                        help='source of the configs (default: %(default)s)')
    parser.add_argument('--tag', default=settings.config_tag(),
                        help='release tag, used when source=release (default: %(default)s)')
    parser.add_argument('--branch', default=settings.config_branch(),
                        help='branch name, used when source=branch (default: %(default)s)')
    parser.add_argument('--path', default=settings.config_path(),
                        help='directory inside the branch, used when source=branch (default: branch root)')
    parser.add_argument('--allow-override', action='store_true',
                        help='overwrite configs that already exist locally')
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s',
                        datefmt='%H:%M:%S', level=logging.INFO)
    args = build_parser().parse_args(argv)
    repo: str = args.repo or settings.repository()
    sync_configs(repo, args.source, tag=args.tag, branch=args.branch, path=args.path,
                 allow_override=args.allow_override)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
