#!/usr/bin/env python3
"""Apply the TryVtri Supabase migrations in order.

Usage
-----
    python backend/scripts/apply_migrations.py                # uses SUPABASE_DB_URL
    python backend/scripts/apply_migrations.py --dry-run

Connection
----------
The script reads ``SUPABASE_DB_URL`` from the environment or ``.env``.
Supabase's *direct* host (``db.<ref>.supabase.co``) is IPv6-only; from an
IPv4-only network use the shared pooler in session mode instead::

    postgresql://postgres.<PROJECT_REF>:<password>@aws-<n>-<region>.pooler.supabase.com:5432/postgres

Nothing outside ``migrations/`` is touched, every statement is idempotent and
the script refuses to run if a file contains a ``drop table`` / ``drop
function`` statement unless ``--allow-destructive`` is passed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    print("psycopg is required:  pip install 'psycopg[binary]'", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "migrations"

_DESTRUCTIVE = re.compile(
    r"\bdrop\s+(table|function|schema|database|column)\b", re.IGNORECASE
)
_TRACKING_TABLE = "tryvtri_schema_migrations"


def _load_env() -> None:
    """Populate os.environ from the repo-root .env without overriding real env."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=False)


def migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        raise SystemExit(f"migrations directory not found: {MIGRATIONS_DIR}")
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print what would run")
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="permit files containing DROP statements",
    )
    args = parser.parse_args()

    _load_env()
    url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not url:
        print(
            "SUPABASE_DB_URL is not set.\n"
            "Copy it from the Supabase dashboard: Connect -> Session pooler.\n"
            "Example:\n"
            "  postgresql://postgres.<REF>:<password>"
            "@aws-1-eu-central-1.pooler.supabase.com:5432/postgres",
            file=sys.stderr,
        )
        return 2

    files = migration_files()
    if not files:
        print("no .sql files found", file=sys.stderr)
        return 1

    for path in files:
        sql = path.read_text(encoding="utf-8")
        if not args.allow_destructive and _DESTRUCTIVE.search(sql):
            print(
                f"refusing: {path.name} contains a DROP statement "
                "(pass --allow-destructive to override)",
                file=sys.stderr,
            )
            return 1

    if args.dry_run:
        for path in files:
            print(f"would apply {path.name} ({path.stat().st_size} bytes)")
        return 0

    applied = 0
    with psycopg.connect(url, connect_timeout=20, sslmode="require") as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                f"create table if not exists {_TRACKING_TABLE} ("
                " filename text primary key, applied_at timestamptz not null default now())"
            )
            for path in files:
                cur.execute(
                    f"select 1 from {_TRACKING_TABLE} where filename = %s",
                    (path.name,),
                )
                if cur.fetchone():
                    print(f"skip  {path.name} (already applied)")
                    continue
                print(f"apply {path.name} ...", end=" ", flush=True)
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    f"insert into {_TRACKING_TABLE} (filename) values (%s)",
                    (path.name,),
                )
                conn.commit()
                print("ok")
                applied += 1
    print(f"done — {applied} migration(s) applied, {len(files) - applied} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
