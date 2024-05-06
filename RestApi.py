import json
import logging
from dataclasses import dataclass, field

import requests

from secret.config import this_repo, token

API_URL = 'https://api.github.com'

headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
           'Authorization': token}


def values():
    return repo_values(this_repo)


def update_values(name, value):
    return update_repo_value(this_repo, name, value)


def create_value(name):
    return create_repo_value(this_repo, name)


def assert200(response: requests.Response):
    if response.status_code != 200:
        logging.error(response.content)
        return True
    return False


# https://docs.github.com/rest/actions/variables?apiVersion=2022-11-28#list-repository-variables
def repo_value(repo, name):
    r = requests.get(f'{API_URL}/repos/{repo}/actions/variables/{name}', headers=headers)
    assert200(r)
    json_data = json.loads(r.content)
    return json_data['value']


def repo_values(repo) -> list:
    r = requests.get(f'{API_URL}/repos/{repo}/actions/variables', headers=headers)
    assert200(r)
    json_data = json.loads(r.content)
    logging.info(f'variables of {repo}:\n{[x["name"] for x in json_data["variables"]]}')
    return json_data['variables']


def create_repo_value(repo, name):
    r = requests.post(f'{API_URL}/repos/{repo}/actions/variables', headers=headers,
                      data=json.dumps({'name': name, 'value': 'null'}))
    assert200(r)
    logging.info(f'create value for {repo}: {name}#{r.status_code}')


def update_repo_value(repo, name, value):
    r = requests.patch(f'{API_URL}/repos/{repo}/actions/variables/{name}', headers=headers,
                       data=json.dumps({'name': name, 'value': value}))
    assert200(r)
    logging.info(f'update value for {repo}: {name}#{r.status_code}')


# https://docs.github.com/rest/releases/releases?apiVersion=2022-11-28#list-releases
def list_releases(repo):
    r = requests.get(f'{API_URL}/repos/{repo}/releases', headers=headers)
    if assert200(r):
        return None
    json_data = json.loads(r.content)
    logging.info(f'{repo} has {len(json_data)} releases at least')
    return json_data


def get_release_by_tag(repo, tag):
    r = requests.get(f'{API_URL}/repos/{repo}/releases/tags/{tag}', headers=headers)
    if assert200(r):
        return
    json_data = json.loads(r.content)
    return json_data


def list_tags(repo):
    r = requests.get(f'{API_URL}/repos/{repo}/tags', headers=headers)
    # assert r.status_code == 200, r.content
    if assert200(r):
        return None
    json_data = json.loads(r.content)
    return json_data


# https://docs.github.com/actions/using-workflows/workflow-commands-for-github-actions
class StdCommand:
    @staticmethod
    def simple(name, value):
        print(f'::{name}::{value}')

    @staticmethod
    def debug(content):
        StdCommand.simple('debug', content)

    @staticmethod
    def notice(content):
        StdCommand.simple('notice', content)

    @staticmethod
    def warning(content):
        StdCommand.simple('warning', content)

    @staticmethod
    def error(content):
        StdCommand.simple('error', content)


StdCmd = StdCommand


@dataclass
class ResultData:
    result: bool
    data: dict = field(default_factory=dict)


class AttrDict(dict):
    def __init__(self, **kwargs):
        super().__init__(kwargs)

    @staticmethod
    def from_dict(v: dict) -> 'AttrDict':
        r = AttrDict()
        r.update(v)
        return r

    def __getattr__(self, item):
        return self[item] if item in self.keys() else None

    def __setattr__(self, key, value):
        self[key] = value


RData = ResultData

