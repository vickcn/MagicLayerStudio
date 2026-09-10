-- 001_initial_schema.sql
-- MagicLayerCore Neon Baseline Migration (仿照 audioStudio/audioCore 標準)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. 匿名用戶 Session 表
CREATE TABLE IF NOT EXISTS anonymous_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_token text UNIQUE NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '7 days'),
    rate_limit_state jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- 2. 上傳物件 Metadata 表 (記錄 GCS 直傳資訊)
CREATE TABLE IF NOT EXISTS uploads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid REFERENCES anonymous_sessions(id) ON DELETE SET NULL,
    object_key text NOT NULL,
    filename text NOT NULL,
    content_type text NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 text,
    status text NOT NULL DEFAULT 'prepared', -- prepared | completed | expired
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '2 days')
);

-- 3. Core 分析任務 Job 表
CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id text UNIQUE NOT NULL, -- 12 碼短字串 (如 302036b80229)
    upload_id uuid REFERENCES uploads(id) ON DELETE SET NULL,
    session_id uuid REFERENCES anonymous_sessions(id) ON DELETE SET NULL,
    task_kind text NOT NULL DEFAULT 'pipeline',
    status text NOT NULL DEFAULT 'queued', -- queued | running | completed | failed | cancelled
    progress numeric NOT NULL DEFAULT 0.0,
    progress_text text NOT NULL DEFAULT '排隊中...',
    options jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '2 days')
);

-- 4. 產物 Artifacts 表 (各頁背景、遮罩、透明圖層 GCS 物件對應)
CREATE TABLE IF NOT EXISTS artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id text NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    kind text NOT NULL, -- background | source | layer | layers_json | objects_json | pptx
    relative_path text NOT NULL,
    object_key text NOT NULL,
    content_type text NOT NULL,
    size_bytes bigint,
    sha256 text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '2 days'),
    UNIQUE(job_id, relative_path)
);

-- 索引優化
CREATE INDEX IF NOT EXISTS idx_sessions_token ON anonymous_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_uploads_session_id ON uploads(session_id);
CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_expires_at ON jobs(expires_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_job_id ON artifacts(job_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts(job_id, kind);
