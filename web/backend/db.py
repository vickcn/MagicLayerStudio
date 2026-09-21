"""
Neon/Postgres-backed ownership, session, and Drive-permanence store.

Source of truth for:
  - Google OAuth sessions (replaces the old in-memory dict; survives Vercel
    cold starts across serverless invocations).
  - Job ownership (which signed-in user created a job, or nobody) and its
    permanent-save state (Google Drive folder/file ids).
  - Per-part Drive backups (job_drive_parts) plus a snapshot of the job's
    pages/rebuilt_pptx structure (jobs.pages_manifest), taken at "永久保存"
    time. Core's GCS artifacts and its own result-manifest share one TTL and
    get purged together, so once that happens Core can no longer answer
    "what pages/parts did this job have" either — Neon has to be able to
    answer that on its own from this snapshot, exactly like audioStudio
    keeps a revision's full analysis_artifacts ledger in its own Postgres
    row instead of trusting audioCore's cache to still be there.

Studio does not persist actual pipeline bytes here (backgrounds, layers,
PPTX content) — those stay wherever they already live (local disk in dev,
GCS via Core in production, or the user's own Google Drive once backed up).
Only lightweight ownership/session/manifest rows live here, mirroring the
audioStudio/audioCore pattern (Neon owns Studio-side ownership; the heavy
processing backend owns execution state).

Local development without a configured database URL leaves this module
inert (`is_configured()` False); callers fall back to the pre-existing
in-memory/file based behavior untouched.
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional


def _database_url() -> str:
    return (
        os.environ.get("MAGICLAYER_STUDIO_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()


def is_configured() -> bool:
    return bool(_database_url())


def require_configured_in_deployment() -> None:
    """Vercel deployments must not silently fall back to ephemeral state."""
    if os.environ.get("VERCEL") and not is_configured():
        raise RuntimeError(
            "部署版需要設定 MAGICLAYER_STUDIO_DATABASE_URL 或 DATABASE_URL，"
            "不能讓 job 擁有權與登入 session 只活在記憶體/檔案暫存中"
        )


_pool: Any = None
_pool_lock = threading.Lock()


class _SingleConnFallback:
    """Used when psycopg_pool isn't installed: opens a fresh connection per call."""

    def __init__(self, url: str) -> None:
        self.url = url

    def connection(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.url, row_factory=dict_row, autocommit=True)


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        url = _database_url()
        if not url:
            return None
        from psycopg.rows import dict_row

        try:
            from psycopg_pool import ConnectionPool

            _pool = ConnectionPool(
                url,
                min_size=0,
                max_size=5,
                max_idle=60,
                kwargs={"row_factory": dict_row, "autocommit": True},
                open=True,
            )
        except ImportError:
            _pool = _SingleConnFallback(url)
        return _pool


@contextmanager
def _conn() -> Iterator[Any]:
    pool = _get_pool()
    if pool is None:
        raise RuntimeError("Database not configured (MAGICLAYER_STUDIO_DATABASE_URL / DATABASE_URL unset)")
    if isinstance(pool, _SingleConnFallback):
        conn = pool.connection()
        try:
            yield conn
        finally:
            conn.close()
    else:
        with pool.connection() as conn:
            yield conn


def _fetchone(sql: str, params: tuple = ()) -> Optional[dict]:
    with _conn() as conn:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _fetchall(sql: str, params: tuple = ()) -> list[dict]:
    with _conn() as conn:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def _execute(sql: str, params: tuple = ()) -> None:
    with _conn() as conn:
        conn.execute(sql, params)


# ── Users ─────────────────────────────────────────────────────────────────

def upsert_user(google_sub: str, email: str, name: str, picture_url: str) -> dict:
    return _fetchone(
        """
        INSERT INTO users (google_sub, email, name, picture_url, last_login_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (google_sub) DO UPDATE SET
            email = EXCLUDED.email,
            name = EXCLUDED.name,
            picture_url = EXCLUDED.picture_url,
            last_login_at = now()
        RETURNING id, google_sub, email, name, picture_url, drive_root_folder_id
        """,
        (google_sub, email, name, picture_url),
    )


def get_user(user_id: str) -> Optional[dict]:
    return _fetchone("SELECT * FROM users WHERE id = %s", (user_id,))


def set_user_drive_root_folder(user_id: str, folder_id: str) -> None:
    _execute("UPDATE users SET drive_root_folder_id = %s WHERE id = %s", (folder_id, user_id))


# ── Google sessions (replaces the in-memory _google_sessions dict) ────────

def save_google_session(session_id: str, user_id: str, data: dict) -> None:
    _execute(
        """
        INSERT INTO google_sessions
            (id, user_id, google_sub, name, email, picture_url, access_token, refresh_token, expires_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), now())
        ON CONFLICT (id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            google_sub = EXCLUDED.google_sub,
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            picture_url = EXCLUDED.picture_url,
            access_token = EXCLUDED.access_token,
            -- 沒有新的 refresh_token 時（Google 只在首次同意時核發）保留舊的
            refresh_token = COALESCE(NULLIF(EXCLUDED.refresh_token, ''), google_sessions.refresh_token),
            expires_at = EXCLUDED.expires_at,
            updated_at = now()
        """,
        (
            session_id,
            user_id,
            data.get("sub", ""),
            data.get("name", ""),
            data.get("email", ""),
            data.get("picture", ""),
            data.get("access_token", ""),
            data.get("refresh_token", ""),
            data.get("expires_at", time.time()),
        ),
    )


def get_google_session(session_id: str) -> Optional[dict]:
    return _fetchone("SELECT * FROM google_sessions WHERE id = %s", (session_id,))


def delete_google_session(session_id: str) -> None:
    _execute("DELETE FROM google_sessions WHERE id = %s", (session_id,))


# ── Job ownership ────────────────────────────────────────────────────────

def create_job_ownership(job_id: str, user_id: Optional[str]) -> None:
    _execute(
        """
        INSERT INTO jobs (job_id, user_id, task_kind, status)
        VALUES (%s, %s, 'pipeline', 'queued')
        ON CONFLICT (job_id) DO NOTHING
        """,
        (job_id, user_id),
    )


def get_job_ownership(job_id: str) -> Optional[dict]:
    return _fetchone("SELECT * FROM jobs WHERE job_id = %s", (job_id,))


def list_job_ids_for_owner(user_id: Optional[str], browser_job_ids: list[str]) -> list[str]:
    """已登入：回傳自己擁有的 + 同瀏覽器認領清單中尚未歸屬任何人的。
    未登入：只回傳認領清單中尚未歸屬任何人的（清單空 → 空陣列）。"""
    ids = [str(i).strip() for i in (browser_job_ids or []) if str(i).strip()][:100]
    if user_id:
        rows = _fetchall(
            """
            SELECT job_id FROM jobs
            WHERE user_id = %s OR (user_id IS NULL AND job_id = ANY(%s::text[]))
            ORDER BY created_at DESC
            """,
            (user_id, ids),
        )
    else:
        if not ids:
            return []
        rows = _fetchall(
            "SELECT job_id FROM jobs WHERE user_id IS NULL AND job_id = ANY(%s::text[]) ORDER BY created_at DESC",
            (ids,),
        )
    return [r["job_id"] for r in rows]


def claim_job_for_user(job_id: str, user_id: str) -> None:
    """把一個尚未歸屬任何人的 job 認領給目前登入的使用者（用於永久保存時）。"""
    _execute("UPDATE jobs SET user_id = %s WHERE job_id = %s AND user_id IS NULL", (user_id, job_id))


def mark_job_permanent(job_id: str, drive_folder_id: str, drive_pptx_file_id: str) -> None:
    _execute(
        """
        UPDATE jobs SET is_permanent = true, drive_folder_id = %s, drive_pptx_file_id = %s,
               permanent_saved_at = now(), permanent_save_error = NULL
        WHERE job_id = %s
        """,
        (drive_folder_id, drive_pptx_file_id, job_id),
    )


def mark_job_permanent_error(job_id: str, error: str) -> None:
    _execute("UPDATE jobs SET permanent_save_error = %s WHERE job_id = %s", (error[:2000], job_id))


def delete_job_ownership(job_id: str) -> None:
    _execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))


# ── Job parts backed up to the owner's Google Drive ─────────────────────────
# 記錄每個 Core 解析部件（背景圖、圖層 PNG、layers/objects.json、重建 PPTX）
# 備份到 .MagicLayerStudio Drive 資料夾後對應的 file id；Core 端的 GCS 產物過期
# 後，介面可以改從這裡回載，不必重新分析。

def save_job_drive_part(job_id: str, relative_path: str, drive_file_id: str, content_type: str = "", size_bytes: int = 0) -> None:
    _execute(
        """
        INSERT INTO job_drive_parts (job_id, relative_path, drive_file_id, content_type, size_bytes, synced_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (job_id, relative_path) DO UPDATE SET
            drive_file_id = EXCLUDED.drive_file_id,
            content_type = EXCLUDED.content_type,
            size_bytes = EXCLUDED.size_bytes,
            synced_at = now()
        """,
        (job_id, relative_path, drive_file_id, content_type, size_bytes),
    )


def get_job_drive_part(job_id: str, relative_path: str) -> Optional[dict]:
    return _fetchone(
        "SELECT * FROM job_drive_parts WHERE job_id = %s AND relative_path = %s",
        (job_id, relative_path),
    )


def list_job_drive_parts(job_id: str) -> list[dict]:
    return _fetchall(
        "SELECT * FROM job_drive_parts WHERE job_id = %s ORDER BY relative_path",
        (job_id,),
    )


def save_job_pages_manifest(job_id: str, pages_manifest: list, rebuilt_pptx_relative: Optional[str]) -> None:
    """快照備份當下的 pages/rebuilt_pptx 結構，讓 Core 端過期後仍能獨立重建 result 形狀。"""
    import json as _json

    _execute(
        """
        UPDATE jobs SET pages_manifest = %s, rebuilt_pptx_relative = %s, parts_backed_up_at = now()
        WHERE job_id = %s
        """,
        (_json.dumps(pages_manifest, ensure_ascii=False), rebuilt_pptx_relative, job_id),
    )


# ── Google session lookup by user (background rehydrate; no request cookie) ─

def get_google_session_by_user(user_id: str) -> Optional[dict]:
    return _fetchone(
        "SELECT * FROM google_sessions WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    )
