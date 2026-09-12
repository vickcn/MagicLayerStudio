-- 002_user_accounts_and_permanent_storage.sql
-- MagicLayerStudio Google OAuth Users & Permanent Project Storage Migration

-- 1. 使用者主表 (Google OAuth 登入用戶)
CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    google_sub text UNIQUE NOT NULL,
    email text UNIQUE NOT NULL,
    name text NOT NULL DEFAULT '',
    picture_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz NOT NULL DEFAULT now(),
    settings jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- 2. 登入使用者的持久 Session 表
CREATE TABLE IF NOT EXISTS user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token text UNIQUE NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 days')
);

-- 3. 為 uploads 與 jobs 表擴充 user_id 與 is_permanent 永久保存標記
ALTER TABLE uploads ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE uploads ADD COLUMN IF NOT EXISTS is_permanent boolean NOT NULL DEFAULT false;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_permanent boolean NOT NULL DEFAULT false;

-- 4. 建立常用查詢索引
CREATE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_is_permanent ON jobs(is_permanent);
CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id);
