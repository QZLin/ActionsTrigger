"""Minimal GitHub REST API client plus the small data types shared by the units."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import requests

from .settings import api_url, repository, token


def api_headers() -> dict[str, str]:
    """Request headers for an authenticated GitHub API call."""
    return {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Authorization': token(),
    }


def _url(path: str) -> str:
    return f'{api_url()}/{path.lstrip("/")}'


def get_actions_value() -> list[dict[str, Any]]:
    return repo_values(repository())


def update_values(name: str, value: str) -> None:
    update_repo_value(repository(), name, value)


def create_value(name: str) -> None:
    create_repo_value(repository(), name)


def assert200(response: requests.Response) -> bool:
    """Log a failed response; ``True`` means the request did not succeed."""
    if response.status_code != 200:
        logging.error(response.content)
        return True
    return False


# https://docs.github.com/rest/actions/variables?apiVersion=2022-11-28#list-repository-variables
def repo_value(repo: str, name: str) -> str:
    r = requests.get(_url(f'repos/{repo}/actions/variables/{name}'), headers=api_headers())
    assert200(r)
    json_data = json.loads(r.content)
    return json_data['value']


def repo_values(repo: str) -> list[dict[str, Any]]:
    r = requests.get(_url(f'repos/{repo}/actions/variables'), headers=api_headers())
    assert200(r)
    json_data = json.loads(r.content)
    logging.info(f'variables of {repo}:\n{[x["name"] for x in json_data["variables"]]}')
    return json_data['variables']


def create_repo_value(repo: str, name: str) -> None:
    r = requests.post(_url(f'repos/{repo}/actions/variables'), headers=api_headers(),
                      data=json.dumps({'name': name, 'value': 'null'}))
    assert200(r)
    logging.info(f'create value for {repo}: {name}#{r.status_code}')


def update_repo_value(repo: str, name: str, value: str) -> None:
    r = requests.patch(_url(f'repos/{repo}/actions/variables/{name}'), headers=api_headers(),
                       data=json.dumps({'name': name, 'value': value}))
    assert200(r)
    logging.info(f'update value for {repo}: {name}#{r.status_code}')


# https://docs.github.com/rest/releases/releases?apiVersion=2022-11-28#list-releases
def list_releases(repo: str) -> list[dict[str, Any]] | None:
    r = requests.get(_url(f'repos/{repo}/releases'), headers=api_headers())
    if assert200(r):
        return None
    json_data = json.loads(r.content)
    logging.info(f'{repo} has {len(json_data)} releases at least')
    return json_data


def get_release_by_tag(repo: str, tag: str) -> dict[str, Any] | None:
    r = requests.get(_url(f'repos/{repo}/releases/tags/{tag}'), headers=api_headers())
    if assert200(r):
        return None
    return json.loads(r.content)


def list_tags(repo: str) -> list[dict[str, Any]] | None:
    r = requests.get(_url(f'repos/{repo}/tags'), headers=api_headers())
    # assert r.status_code == 200, r.content
    if assert200(r):
        return None
    return json.loads(r.content)


# https://docs.github.com/rest/repos/contents?apiVersion=2022-11-28#get-repository-content
def list_contents(repo: str, path: str = '', ref: str | None = None) -> list[dict[str, Any]] | None:
    """List the entries of a directory at ``ref`` (a file yields a single entry).

    Returns ``None`` when the path does not exist in that ref.
    """
    sub_path = path.strip('/')
    r = requests.get(_url(f'repos/{repo}/contents{f"/{sub_path}" if sub_path else ""}'),
                     headers=api_headers(),
                     params={'ref': ref} if ref else None)
    if r.status_code == 404:
        logging.warning(f'{repo}#{ref or "default"}:{sub_path or "/"} not found')
        return None
    if assert200(r):
        return None
    json_data = json.loads(r.content)
    return json_data if isinstance(json_data, list) else [json_data]


# https://docs.github.com/actions/using-workflows/workflow-commands-for-github-actions
class ActionsCmd:
    @staticmethod
    def simple(name: str, value: str) -> None:
        print(f'::{name}::{value}')

    @staticmethod
    def info(content: str) -> None:
        print(content)

    @staticmethod
    def debug(content: str) -> None:
        ActionsCmd.simple('debug', content)

    @staticmethod
    def notice(content: str) -> None:
        ActionsCmd.simple('notice', content)

    @staticmethod
    def warning(content: str) -> None:
        ActionsCmd.simple('warning', content)

    @staticmethod
    def error(content: str) -> None:
        ActionsCmd.simple('error', content)


StdCmd = ActionsCmd


@dataclass
class ResultData:
    ok: bool
    unit_data: dict = field(default_factory=dict)


class AttrDict(dict):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(kwargs)

    @staticmethod
    def from_dict(v: dict) -> 'AttrDict':
        r = AttrDict()
        r.update(v)
        return r

    def __getattr__(self, item: str) -> Any:
        return self[item] if item in self else None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value
