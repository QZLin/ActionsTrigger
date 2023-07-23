import json
import logging

import requests

from secret.config import this_repo, token

API = 'https://api.github.com'

headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
           'Authorization': token}


def values():
    return repo_values(this_repo)


def update_values(name, value):
    return update_repo_value(this_repo, name, value)


def create_value(name):
    return create_repo_value(this_repo, name)


def assert200(r: requests.Response):
    if r.status_code != 200:
        logging.error(r.content)
        return True
    return False


# https://docs.github.com/rest/actions/variables?apiVersion=2022-11-28#list-repository-variables
def repo_value(repo, name):
    r = requests.get(f'{API}/repos/{repo}/actions/variables/{name}', headers=headers)
    json_data = json.loads(r.content)
    return json_data['value']


def repo_values(repo) -> list:
    r = requests.get(f'{API}/repos/{repo}/actions/variables', headers=headers)
    json_data = json.loads(r.content)
    logging.info(f'variables of {repo}:\n{[x["name"] for x in json_data["variables"]]}')
    return json_data['variables']


def create_repo_value(repo, name):
    r = requests.post(f'{API}/repos/{repo}/actions/variables', headers=headers,
                      data=json.dumps({'name': name, 'value': 'null'}))
    logging.info(f'create value for {repo}: {name}#{r.status_code}')


def update_repo_value(repo, name, value):
    r = requests.patch(f'{API}/repos/{repo}/actions/variables/{name}', headers=headers,
                       data=json.dumps({'name': name, 'value': value}))
    logging.info(f'update value for {repo}: {name}#{r.status_code}')


# https://docs.github.com/rest/releases/releases?apiVersion=2022-11-28#list-releases
def list_releases(repo):
    r = requests.get(f'{API}/repos/{repo}/releases', headers=headers)
    if r.status_code != 200:
        logging.error(r.content)
        return None
    json_data = json.loads(r.content)
    logging.info(f'{repo} has {len(json_data)} releases at least')
    return json_data


def get_release_by_tag(repo, tag):
    r = requests.get(f'{API}/repos/{repo}/releases/tags/{tag}', headers=headers)
    if assert200(r):
        return
    json_data = json.loads(r.content)
    return json_data


def list_tags(repo):
    r = requests.get(f'{API}/repos/{repo}/tags', headers=headers)
    # assert r.status_code == 200, r.content
    if r.status_code != 200:
        logging.error(r.content)
        return None
    json_data = json.loads(r.content)
    return json_data
