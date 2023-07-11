import json
import logging

import requests

from secret.config import this_repo, token

headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
           'Authorization': token}


def values():
    return repo_values(this_repo)


def update_values(name, value):
    return update_repo_value(this_repo, name, value)


def create_value(name):
    return create_repo_value(this_repo, name)


# https://docs.github.com/rest/actions/variables?apiVersion=2022-11-28#list-repository-variables
def repo_value(repo, name):
    r = requests.get(f'https://api.github.com/repos/{repo}/actions/variables/{name}', headers=headers)
    json_data = json.loads(r.content)
    return json_data['value']


def repo_values(repo) -> list:
    r = requests.get(f'https://api.github.com/repos/{repo}/actions/variables', headers=headers)
    json_data = json.loads(r.content)
    logging.info(f'variables of {repo}:\n{[x["name"] for x in json_data["variables"]]}')
    return json_data['variables']


def create_repo_value(repo, name):
    r = requests.post(f'https://api.github.com/repos/{repo}/actions/variables', headers=headers,
                      data=json.dumps({'name': name, 'value': 'null'}))
    logging.info(f'create value for {repo}: {name}#{r.status_code}')


def update_repo_value(repo, name, value):
    r = requests.patch(f'https://api.github.com/repos/{repo}/actions/variables/{name}', headers=headers,
                       data=json.dumps({'name': name, 'value': value}))
    logging.info(f'update value for {repo}: {name}#{r.status_code}')
