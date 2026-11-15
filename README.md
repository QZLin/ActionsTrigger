# ActionsTrigger

Personal GitHub Actions trigger & upstream event subscriber.

Poll upstream repositories on a schedule and dispatch GitHub Actions workflows when
something changed upstream. A **unit** couples a *condition* ("did the upstream
change?") with one or more *actions* ("dispatch these workflows"), and keeps its
state in the repository's Actions variables, so no database is needed.

* runs from a GitHub Actions schedule (every 30 minutes by default)
* unit definitions live in plain yaml and can be pulled from a release or a branch
* conditions/actions are small modules that can be added without touching the core
* per-unit state is a single Actions variable named after the unit id
* annotations (`::notice::`, `::warning::`, `::error::`) show up in the Actions UI

## How it works

```
config/*.yaml ──► for every unit ──► condition.handle(condition_args, state)
                        │                       │ ok?
                        │                       ├─ no  ──► ::notice::#UNIT skipped
                        │                       └─ yes ──► actions[].handle(action_args, state)
                        └──► state changed? ──► update the UNIT Actions variable
```

The state is read from the Actions variable `UNIT_ID` before the condition runs and
is written back only when it actually changed, so one run costs at most one write
per changed unit.

## Requirements

* Python >= 3.14
* [uv](https://docs.astral.sh/uv/)

## Install & develop

```pwsh
uv sync                                  # create .venv and install the package (editable)
uv run python -m unittest discover -s tests -v
```

## Quick start

```pwsh
Copy-Item .env.example .env              # fill in ACTIONS_TRIGGER_REPO / ACTIONS_TRIGGER_TOKEN
Copy-Item config.example.yaml config/units.yaml
uv run actions_trigger-ext-config        # optional: pull the configs from GitHub
uv run actions_trigger                   # or: uv run python -m actions_trigger
```

## Structure

```
|--- src/actions_trigger            <- the package (installed via `uv sync`)
|   |--- __init__.py                <- __version__
|   |--- __main__.py                <- `python -m actions_trigger`
|   |--- main.py                    <- unit loop, console script `actions_trigger`
|   |--- rest_api.py                <- GitHub REST helpers, ResultData, ActionsCmd, AttrDict
|   |--- settings.py                <- env var / .env settings
|   |--- external_config.py         <- config downloader, console script `actions_trigger-ext-config`
|   |--- script/                    <- handlers referenced by name from the configs
|--- config                         <- unit definitions (yaml), scanned at runtime, git-ignored
|--- config.example.yaml            <- example unit file
|--- .env.example                   <- example settings
|--- tests
```

`config/` is deliberately not tracked by this repository: it is usually a checkout
of the `config` branch, or the result of `actions_trigger-ext-config`.

## Settings

Nothing is validated at import time; a missing setting raises
`MissingSettingError` when the value is first used (`actions_trigger` exits with
code 2). Values are read from the environment first, then from `.env`
(`ACTIONS_TRIGGER_ENV_FILE`, existing variables always win).

| Variable                        | Fallback                   | Default                  | Meaning                                                        |
|---------------------------------|----------------------------|--------------------------|----------------------------------------------------------------|
| `ACTIONS_TRIGGER_REPO`          | `GITHUB_REPOSITORY`        | – (required)             | Repository whose Actions variables hold the unit state         |
| `ACTIONS_TRIGGER_TOKEN`         | `GITHUB_TOKEN`, `GH_TOKEN` | – (required)             | Token for the REST API                                         |
| `ACTIONS_TRIGGER_API_URL`       | `GITHUB_API_URL`           | `https://api.github.com` | REST base URL, used by `rest_api`                              |
| `ACTIONS_TRIGGER_CONFIG_DIR`    | –                          | `config`                 | Directory scanned for unit definitions                         |
| `ACTIONS_TRIGGER_DEBUG`         | `_DEBUG` file              | off                      | Verbose logging (`1`/`true`/`yes`/`on`)                        |
| `ACTIONS_TRIGGER_ENV_FILE`      | –                          | `.env`                   | Alternative dotenv file                                        |
| `ACTIONS_TRIGGER_CONFIG_SOURCE` | –                          | `release`                | `release` or `branch`, see [External config](#external-config) |
| `ACTIONS_TRIGGER_CONFIG_TAG`    | –                          | `store-config`           | Release tag for `source=release`                               |
| `ACTIONS_TRIGGER_CONFIG_BRANCH` | –                          | `config`                 | Branch for `source=branch`                                     |
| `ACTIONS_TRIGGER_CONFIG_PATH`   | –                          | branch root              | Directory inside the branch                                    |

The token needs *Variables: read/write* on `ACTIONS_TRIGGER_REPO`, read access to
the watched releases/contents, and *Actions: write* to dispatch workflows.

## Unit definitions

Every file in the config directory is parsed as YAML and must be a mapping of
unit id to unit definition:

```yaml
unique_id:
  type: simple
  condition:
    name: simple_new_commit
    repo: owner/upstream
    branch: main
  actions:
    - name: workflow_dispatch
      repo: owner/fork
      branch: sync
      id: sync.yml
    - name: workflow_dispatch
      repo: owner/mirror
      branch: main
      id: mirror.yaml
```

| Key         | Meaning                                                                |
|-------------|------------------------------------------------------------------------|
| `<unit id>` | mapping key; upper-cased in logs and used as the Actions variable name |
| `type`      | unit handler, currently only `simple`                                  |
| `condition` | mapping whose `name` is a module in `script/`                          |
| `actions`   | list of action mappings, each with a `name` of a module in `script/`   |
| `action`    | legacy single action mapping; ignored when `actions` is present        |

Remaining keys of `condition` / `actions[i]` are passed to that handler verbatim.

Behavior worth knowing:

* conditions get a *copy* of the stored state and may mutate it; all state
  changes (from the condition and all actions) are persisted together once
* actions run **in order**, each receiving the same state; a failing action (`ok=False`) is reported as
  `::warning::#UNIT action <name> failed` and does
  not stop the remaining ones
* the summary annotation is `::notice::#UNIT executed 2/3 action(s)` or
  `::notice::#UNIT skipped`
* a unit that is not known yet gets its Actions variable created with the value
  `null`, which means "empty state"
* files are processed in sorted order; an empty file only warns, a unit without
  `type` or with an unknown `type` is reported and skipped
* exit codes: `0` success, `1` config directory missing (or an unexpected
  exception), `2` missing settings

## Handlers

A handler is a module in `src/actions_trigger/script/` exposing
`handle(args, unit_data) -> ResultData`. Conditions and actions are
interchangeable - any handler can be used in either position.

### Conditions

| `name`               | Args                                        | True when                                      | State written     |
|----------------------|---------------------------------------------|------------------------------------------------|-------------------|
| `simple_new_commit`  | `repo`, `branch`                            | head commit sha differs from the stored one    | `last_commit_sha` |
| `simple_new_tag`     | `repo`                                      | newest tag differs from the stored one         | `last_tag`        |
| `simple_new_release` | `repo`, `allow_prerelease` (must be `true`) | newest release tag differs from the stored one | `last_tag`        |
| `curl_hash_changed`  | `url`, optional `headers`                   | sha256 of the body differs from the stored one | `last_hash`       |
| `basic_condition`    | –                                           | always                                         | –                 |

### Actions

| `name`              | Args                                   | Effect                                                |
|---------------------|----------------------------------------|-------------------------------------------------------|
| `workflow_dispatch` | `repo`, `id` (workflow file), `branch` | creates a `workflow_dispatch` event for that workflow |
| `echo`              | `content`                              | prints the content (useful to test a new unit)        |
| `basic_action`      | –                                      | does nothing                                          |

### Writing your own

```python
from ..rest_api import ResultData


def handle(args: dict, unit_data: dict) -> ResultData:
    if args['something'] == unit_data.get('last_something'):
        return ResultData(False)  # nothing changed
    unit_data['last_something'] = args['something']
    return ResultData(True, unit_data)  # changed; state is persisted
```

Drop the file into `script/` and reference it by module name. Helpers available
in `rest_api`: `api_headers()`, `list_releases()`, `list_tags()`,
`get_release_by_tag()`, `repo_values()`, `create_value()`, `update_values()`,
`list_contents()`, plus `ActionsCmd` for workflow annotations.

## External config

`actions_trigger-ext-config` copies yaml configs into the config directory:

```pwsh
uv run actions_trigger-ext-config                                   # repo + source from settings
uv run actions_trigger-ext-config owner/repo -s branch --branch config --path units
uv run actions_trigger-ext-config owner/repo -s release --tag store-config --allow-override
```

| Option              | Default                | Meaning                                          |
|---------------------|------------------------|--------------------------------------------------|
| `repo` (positional) | `ACTIONS_TRIGGER_REPO` | Repository holding the configs                   |
| `-s`, `--source`    | `release`              | `release` or `branch`                            |
| `--tag`             | `store-config`         | Release whose assets are used (`source=release`) |
| `--branch`          | `config`               | Branch holding the files (`source=branch`)       |
| `--path`            | branch root            | Directory inside the branch (`source=branch`)    |
| `--allow-override`  | off                    | Overwrite configs that already exist locally     |

* only `*.yaml` / `*.yml` files are taken; directories and other assets are skipped
* the listing is not recursive
* existing local files win unless `--allow-override` is given, so manual fixes
  are never silently replaced
* names that would escape the config directory are rejected
* the files are downloaded from the URLs returned by the API (no auth on the
  download itself), so the config repository must be publicly readable

## CI

`.github/workflows/main.yml` runs the whole thing every 30 minutes (also on push
to `main` and on demand):

1. `uv sync`
2. `uv run actions_trigger-ext-config "${{ github.repository }}" --source branch`
3. `uv run actions_trigger-ext-config "${{ github.repository }}" --source release`
4. `uv run actions_trigger`

`GITHUB_TOKEN` is provided to the job from `secrets.PERSONALTOKEN`, and
`GITHUB_REPOSITORY` is set by Actions automatically - both are picked up by
`settings.py`. The workflow needs `permissions: write-all` because it writes
Actions variables.

## Tests

```pwsh
uv run python -m unittest discover -s tests -v
```

| File                              | Covers                                                                             |
|-----------------------------------|------------------------------------------------------------------------------------|
| `tests/test_main.py`              | unit loop: `actions` list order, failing actions, state merging, config validation |
| `tests/test_external_config.py`   | release/branch sources, yaml filtering, no-override, unsafe names                  |
| `tests/test_rest_api.py`          | `AttrDict`                                                                         |
| `tests/test_curl_hash_changed.py` | a real HTTP round trip; skipped when the network is unavailable                    |

## Known limitations

* only the `simple` unit type is implemented
* `workflow_dispatch` and `simple_new_commit` still hardcode `api.github.com`,
  so GitHub Enterprise is not fully supported
* HTTP calls have no timeout
* a unit's whole state is stored in one Actions variable, so keep it small

## License

LGPL-2.1, see [LICENSE](LICENSE).
