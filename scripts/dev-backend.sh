#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../backend"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://rigstory:rigstory@localhost:5432/rigstory}"

alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
