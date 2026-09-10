# SimLeague — Setup and Commands

macOS, uv-managed. Repo lives at `~/Developer/SimLeague`, importable package is
`simleague`.

---

## One-time, machine level

```bash
brew install uv
```

## Project setup

```bash
cd ~/Developer/SimLeague
git init                                # if not already a repo
uv init --package --name simleague
uv venv --python 3.12
source .venv/bin/activate
```

The folder is `SimLeague` but the package name is lowercase `simleague`. Mixed
case works on macOS and Windows (case-insensitive filesystems) and then fails
on Linux CI.

## Dependencies

```bash
uv add fastapi uvicorn asyncpg pydantic-settings
uv add --dev pytest pytest-asyncio httpx ruff mypy testcontainers
```

Use `uv add`, not `pip install`. Both install into the venv, but only `uv add`
records the dependency in `pyproject.toml` and `uv.lock`.

## Directory scaffold

```bash
mkdir -p src/simleague/{domain,ports,app,adapters/postgres,adapters/ingest,api/routers}
mkdir -p sql/{migrations,queries} tests data/raw

touch src/simleague/{domain,ports,app,api}/__init__.py
touch src/simleague/adapters/__init__.py
touch src/simleague/adapters/{postgres,ingest}/__init__.py
touch src/simleague/api/routers/__init__.py
```

Resulting shape:

```
SimLeague/
├── pyproject.toml          # name = "simleague"
├── uv.lock
├── .gitignore
├── src/
│   └── simleague/
│       ├── domain/         # pure, imports nothing below it
│       ├── ports/          # protocols
│       ├── app/            # use cases
│       ├── adapters/       # postgres, ingest
│       └── api/            # main.py, deps.py, schemas.py, routers/
├── sql/
│   ├── migrations/
│   └── queries/
├── tests/
└── data/raw/               # bronze layer, tracked in git
```

## Running it

```bash
uv sync                                              # installs the package editable
uvicorn simleague.api.main:app --reload --reload-dir src
```

The module path is `simleague.api.main:app`, not `main:app` — `main:app` looks
for a top-level module and fails. `--reload-dir src` stops the reloader from
restarting on changes to `sql/` and `data/`.

## Day to day

```bash
source .venv/bin/activate     # or skip and prefix commands with: uv run
deactivate

uv add <package>
uv sync                       # rebuild env from the lockfile
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
```

`uv run <cmd>` works without activating and syncs the environment first if the
lockfile changed.

## Sanity checks

```bash
which python                  # ~/Developer/SimLeague/.venv/bin/python
rm -rf .venv && uv sync       # proves nothing undeclared was propping it up
```

## Not covered by the venv

- Homebrew packages (`postgresql@16` for `psql`, Docker, `libpq`) — system-wide,
  not in `uv.lock`, document them as prerequisites in the README
- `uv tool install` tools — global tool directory, not the project venv
- `node_modules/` for the React explorer — entirely separate

## Windows equivalent (bot machine)

```powershell
.venv\Scripts\activate
```

---

## .gitignore

Goes at the repo root before the first commit.

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
*.egg
.eggs/

# Virtual environments
.venv/
venv/
env/
ENV/

# uv
.uv/
# keep uv.lock committed -- it is the reproducibility record

# Testing and type checking
.pytest_cache/
.coverage
.coverage.*
coverage.xml
htmlcov/
.mypy_cache/
.dmypy.json
dmypy.json
.ruff_cache/
.hypothesis/

# Environment and secrets
.env
.env.*
!.env.example
*.pem
secrets/

# Local databases and derived data
*.db
*.sqlite
*.sqlite3
*.duckdb
*.duckdb.wal
data/warehouse/
data/staging/
data/derived/
dumps/
*.dump
*.sql.gz

# Keep raw captures -- this is the bronze layer, it is the source of truth
!data/raw/
!data/raw/**

# Terraform
.terraform/
*.tfstate
*.tfstate.*
.terraform.lock.hcl
*.tfvars
!*.tfvars.example

# dbt
target/
dbt_packages/
logs/

# Editors
.vscode/
.idea/
*.swp
*.swo
.cursor/
.cursorignore

# macOS
.DS_Store
.AppleDouble
.LSOverride
._*
.Spotlight-V100
.Trashes

# Windows (the bot machine)
Thumbs.db
Desktop.ini

# Node, if the React explorer lives in this repo
node_modules/
.next/
*.tsbuildinfo
```

Two deliberate choices in there: the `data/raw/` negation keeps raw captures
tracked while everything derived is ignored, so the database stays rebuildable
from git; and `uv.lock` is committed so the Mac and the Windows bot machine
agree on versions.