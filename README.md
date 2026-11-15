# ActionsTrigger

Personal actions trigger / upstream event subscriber

```
> Structure

|--- src/actionstrigger          <- the package (installed via `uv sync`)
|   |--- __main__.py             <- `python -m actionstrigger`
|   |--- main.py                 <- unit loop, console script `actionstrigger`
|   |--- rest_api.py             <- GitHub REST helpers, ResultData, ActionsCmd
|   |--- settings.py             <- env var / .env settings
|   |--- external_config.py      <- config downloader, console script `actionstrigger-fetch-config`
|   |--- script/                 <- handlers referenced by name from the configs
|--- config                      <- unit definitions (yaml), scanned at runtime
|--- tests
```

## Usage

```pwsh
. ./init.ps1                 # uv sync
uv run actionstrigger-fetch-config   # optional: pull configs from GitHub (see below)
uv run actionstrigger        # or: uv run python -m actionstrigger
uv run python -m unittest discover -s tests -v
```

Settings come from environment variables, falling back to `.env` — see
`.env.example`: `ACTIONS_TRIGGER_REPO` (defaults to `GITHUB_REPOSITORY`),
`ACTIONS_TRIGGER_TOKEN` (defaults to `GITHUB_TOKEN` / `GH_TOKEN`),
`ACTIONS_TRIGGER_CONFIG_DIR` (default `config`) and `ACTIONS_TRIGGER_DEBUG`.

### External config

`actionstrigger-fetch-config [repo] [-s release|branch] [--tag TAG] [--branch BRANCH] [--path DIR] [--allow-override]`
copies the yaml configs into the config directory; existing files are kept
unless `--allow-override` is given.

| `--source` | reads from | defaults |
| --- | --- | --- |
| `release` | `*.yaml` / `*.yml` assets of a release | `--tag store-config` |
| `branch` | `*.yaml` / `*.yml` files of a directory in a branch | `--branch config --path` (branch root) |

The defaults can be overridden with `ACTIONS_TRIGGER_CONFIG_SOURCE`,
`ACTIONS_TRIGGER_CONFIG_TAG`, `ACTIONS_TRIGGER_CONFIG_BRANCH` and
`ACTIONS_TRIGGER_CONFIG_PATH`. `repo` defaults to `ACTIONS_TRIGGER_REPO`.

## Main

### Script

#### Unit

* id
* handler
* args
