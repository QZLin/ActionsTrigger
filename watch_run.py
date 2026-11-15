"""Throwaway: watch a workflow run until it finishes and print its annotations."""
import sys
import time

import requests

from actions_trigger import settings

SHA = sys.argv[1] if len(sys.argv) > 1 else ''
h = {'Authorization': settings.token(), 'Accept': 'application/vnd.github+json'}
repo = settings.repository()


def runs(limit=6):
    r = requests.get(f'https://api.github.com/repos/{repo}/actions/workflows/main.yml/runs',
                     headers=h, params={'per_page': limit}, timeout=20)
    return r.json().get('workflow_runs', [])


def wait(sha, timeout=900):
    deadline = time.time() + timeout
    target = None
    while time.time() < deadline:
        for x in runs():
            if not sha or x['head_sha'].startswith(sha):
                target = x
                break
        if target and target['status'] == 'completed':
            return target
        time.sleep(15)
    return target


def show(run):
    print(f"run #{run['id']} event={run['event']} status={run['status']} conclusion={run['conclusion']} sha={run['head_sha'][:7]}")
    jobs = requests.get(f"https://api.github.com/repos/{repo}/actions/runs/{run['id']}/jobs", headers=h, timeout=20).json()
    for job in jobs.get('jobs', []):
        print(f"  job {job['name']}: {job['conclusion']}")
        for s in job.get('steps', []):
            flag = 'OK ' if s['conclusion'] == 'success' else str(s['conclusion']).upper()
            print(f"    {s['number']:>2} {s['name']:<22} {flag}")
        a = requests.get(f"https://api.github.com/repos/{repo}/check-runs/{job['id']}/annotations",
                         headers=h, timeout=20).json()
        print(f"  annotations ({len(a)}):")
        for x in a:
            print(f"    [{x['annotation_level']}] {x['message'][:200]}")


run = wait(SHA)
if run:
    show(run)
else:
    print('no run found')
