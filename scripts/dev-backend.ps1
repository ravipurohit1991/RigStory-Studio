$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot/../backend"

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

if (-not $env:DATABASE_URL) {
  $env:DATABASE_URL = "postgresql+psycopg://rigstory:rigstory@localhost:5432/rigstory"
}

& .\.venv\Scripts\python.exe -m alembic upgrade head
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
