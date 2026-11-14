# claudyboi

Python project managed with [uv](https://docs.astral.sh/uv/). uv installs the
Python version pinned in `.python-version` (3.13) if it is not already present.

## Setup

```bash
# Install uv (skip if already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python 3.13 (uv-managed) and the project's dependencies into .venv
uv sync
```

## Run

```bash
uv run main.py
```

## Add a dependency

```bash
uv add <package>
```
