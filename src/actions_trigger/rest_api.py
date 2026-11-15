"""Minimal GitHub REST API client plus the small data types shared by the units."""

from __future__ import annotations

import json
import logging
import re
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


_VARIABLE_NAME_INVALID = re.compile(r'[^0-9A-Za-z_]')


def variable_name(name: str) -> str:
    """Turn ``name`` into a legal Actions variable name.

    GitHub only allows alphanumerics and underscores, and the name must not start
    with a digit: ``dsh-workspace-migrate`` becomes ``DSH_WORKSPACE_MIGRATE``.
    """
    cleaned = _VARIABLE_NAME_INVALID.sub('_', name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f'_{cleaned}'
    return cleaned


def get_actions_value() -> list[dict[str, Any]]:
    return repo_values(repository())


def update_values(name: str, value: str) -> None:
    update_repo_value(repository(), variable_name(name), value)


def create_value(name: str) -> None:
    create_repo_value(repository(), variable_name(name))


def assert200(response: requests.Response) -> bool:
    """Log a failed response; ``True`` means the request did not succeed."""
    if response.status_code != 200:
        logging.error(response.content)
        return True
    return False


class ApiError(RuntimeError):
    """Raised when the REST API answers with an unexpected status."""

    def __init__(self, what: str, response: requests.Response):
        message = ''
        try:
            message = response.json().get('message', '')
        except ValueError:
            message = response.text[:200]
        super().__init__(f'{what} failed with {response.status_code}: {message or response.content!r}')
        self.status = response.status_code


def _expect(response: requests.Response, what: str, *codes: int) -> None:
    """Raise :class:`ApiError` and annotate the failure unless the status is expected."""
    if response.status_code in codes:
        return
    error = ApiError(what, response)
    logging.error(error)
    ActionsCmd.error(str(error))
    raise error


def _next_page(response: requests.Response) -> str | None:
    """Extract the ``rel="next"`` URL from the Link header, if any."""
    for part in (response.headers.get('Link') or '').split(','):
        if 'rel="next"' in part:
            return part.split(';')[0].strip().strip('<>')
    return None


# https://docs.github.com/rest/actions/variables?apiVersion=2022-11-28#list-repository-variables
def repo_value(repo: str, name: str) -> str:
    r = requests.get(_url(f'repos/{repo}/actions/variables/{name}'), headers=api_headers())
    _expect(r, f'get variable {name} of {repo}', 200)
    return json.loads(r.content)['value']


def repo_values(repo: str) -> list[dict[str, Any]]:
    """Every variable of ``repo``, following pagination."""
    url: str | None = _url(f'repos/{repo}/actions/variables')
    params: dict[str, int] | None = {'per_page': 100}
    variables: list[dict[str, Any]] = []
    while url:
        r = requests.get(url, headers=api_headers(), params=params)
        _expect(r, f'list variables of {repo}', 200)
        variables.extend(json.loads(r.content).get('variables') or [])
        url = _next_page(r)
        params = None  # the next page url already carries the query
    logging.info(f'variables of {repo}:\n{[x["name"] for x in variables]}')
    return variables


def create_repo_value(repo: str, name: str) -> None:
    r = requests.post(_url(f'repos/{repo}/actions/variables'), headers=api_headers(),
                      data=json.dumps({'name': name, 'value': 'null'}))
    if r.status_code == 409:  # the variable already exists, nothing to create
        logging.debug(f'variable {name} of {repo} already exists')
        return
    _expect(r, f'create variable {name} of {repo}', 200, 201, 204)
    logging.info(f'create value for {repo}: {name}#{r.status_code}')


def update_repo_value(repo: str, name: str, value: str) -> None:
    r = requests.patch(_url(f'repos/{repo}/actions/variables/{name}'), headers=api_headers(),
                       data=json.dumps({'name': name, 'value': value}))
    _expect(r, f'update variable {name} of {repo}', 200, 204)
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


# https://docs.github.com/rest/actions/workflow-runs?apiVersion=2022-11-28#delete-a-workflow-run
def delete_workflow_run(repo: str, run_id: int) -> bool:
    """Delete one workflow run; ``True`` when it was deleted by this call."""
    r = requests.delete(_url(f'repos/{repo}/actions/runs/{run_id}'), headers=api_headers())
    if r.status_code == 204:
        logging.info(f'deleted run {run_id} of {repo}')
        return True
    if r.status_code == 404:
        logging.warning(f'run {run_id} of {repo} not found, keep going')
        return False
    logging.error(f'delete run {run_id} of {repo} failed: {r.status_code} {r.content}')
    ActionsCmd.error(f'delete run {run_id} of {repo} failed with {r.status_code}')
    return False


# https://docs.github.com/rest/actions/workflow-runs?apiVersion=2022-11-28#get-a-workflow-run
def get_workflow_run(repo: str, run_id: int) -> dict[str, Any] | None:
    r = requests.get(_url(f'repos/{repo}/actions/runs/{run_id}'), headers=api_headers())
    if r.status_code == 404:
        return None
    if assert200(r):
        return None
    return json.loads(r.content)


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
