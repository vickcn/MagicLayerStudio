#!/usr/bin/env python3
"""
Simple and reliable SQL migration runner for MagicLayerCore Neon Database.
Compatible with PostgreSQL (Neon) and uses psycopg2 / pg8000 / psql as fallback.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def get_db_url() -> str:
    url = (
        os.environ.get("MAGICLAYER_STUDIO_DATABASE_URL")
        or os.environ.get("MAGICLAYER_DATABASE_URL")
        or os.environ.get("MAGICLAYER_CORE_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        # Check local .env file
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DATABASE_URL=") or line.startswith("MAGICLAYER_STUDIO_DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if url:
                        break
    if not url:
        # Check local .neon connection string file if present
        neon_file = PROJECT_ROOT / ".neon"
        if neon_file.exists():
            url = neon_file.read_text(encoding="utf-8").strip()

    if not url:
        # Fallback to GCP Secret Manager if project is configured
        import subprocess
        for secret_name in ("MAGICLAYER_STUDIO_DATABASE_URL", "MAGICLAYER_DATABASE_URL"):
            try:
                res = subprocess.run(
                    ["gcloud", "secrets", "versions", "access", "latest", f"--secret={secret_name}", "--project=magiclayer-studio-6826"],
                    capture_output=True, text=True, check=True
                )
                url = res.stdout.strip()
                if url:
                    break
            except Exception:
                pass
    if not url:
        print("[ERROR] DATABASE_URL or MAGICLAYER_STUDIO_DATABASE_URL is not set.")
        sys.exit(1)
    return url


def run_migrations():
    db_url = get_db_url()
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("[INFO] No migration files found.")
        return

    print(f"[INFO] Connecting to Neon Database...")
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
    except ImportError:
        # Fallback to urllib / psql if psycopg2 not installed
        import subprocess
        for mf in migration_files:
            print(f"[MIGRATE] Applying {mf.name} via psql...")
            subprocess.run(["psql", db_url, "-f", str(mf)], check=True)
        print("[SUCCESS] All migrations applied!")
        return

    # Create schema migrations table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            version text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        );
    """)

    for mf in migration_files:
        cur.execute("SELECT 1 FROM _schema_migrations WHERE version = %s", (mf.name,))
        if cur.fetchone():
            print(f"  - {mf.name}: already applied (skip)")
            continue

        print(f"  -> Applying {mf.name}...")
        sql_content = mf.read_text(encoding="utf-8")
        cur.execute(sql_content)
        cur.execute("INSERT INTO _schema_migrations (version) VALUES (%s)", (mf.name,))
        print(f"  ✓ {mf.name} applied successfully!")

    cur.close()
    conn.close()
    print("[SUCCESS] Database migrations completed!")


if __name__ == "__main__":
    run_migrations()
