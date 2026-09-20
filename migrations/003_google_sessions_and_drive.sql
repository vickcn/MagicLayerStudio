-- 003_google_sessions_and_drive.sql
-- 持久化 Google OAuth session（取代記憶體 dict，跨 Vercel 冷啟動存活）
-- 以及登入使用者「永久保存到自己 Google Drive」所需欄位（仿照 audioStudio）

-- 1. 持久化 Google Session（取代 _google_sessions in-memory dict）
CREATE TABLE IF NOT EXISTS google_sessions (
    id text PRIMARY KEY, -- = GOOGLE_SESSION_COOKIE 的值
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    google_sub text NOT NULL,
    name text,
    email text,
    picture_url text,
    access_token text,
    refresh_token text,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_google_sessions_sub ON google_sessions(google_sub, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_google_sessions_user_id ON google_sessions(user_id);

-- 2. jobs 表擴充：永久保存到使用者 Google Drive 的狀態
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS drive_folder_id text;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS drive_pptx_file_id text;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS permanent_saved_at timestamptz;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS permanent_save_error text;

-- 3. users 表擴充：快取使用者的 MagicLayerStudio 根資料夾，避免每次都查詢 Drive
ALTER TABLE users ADD COLUMN IF NOT EXISTS drive_root_folder_id text;

CREATE INDEX IF NOT EXISTS idx_jobs_permanent_saved_at ON jobs(permanent_saved_at);
