-- 004_job_drive_parts.sql
-- 把 MagicLayerCore 解析出的部件（背景圖、圖層 PNG、layers.json、objects.json、
-- 重建的 PPTX）依 Core 端相同的相對路徑結構，備份進使用者自己 Google Drive 的
-- .MagicLayerStudio 資料夾，並記錄每個部件對應的 Drive file id。
--
-- Core 端的 GCS 產物與其 result-manifest 共用同一組 TTL，過期時會一起被清除，
-- 所以光记錄「檔案 id」不夠——一旦 Core 端連 pages/rebuilt_pptx 的結構都問不到，
-- Studio 也要能夠自己回答「這個 job 有哪些頁、每頁有哪些部件」。因此額外在
-- jobs 表快照備份當下的 pages/rebuilt_pptx 結構（仿照 audioStudio 把 revision
-- 的 analysis_artifacts 完整記錄在自己的 Postgres，不依賴處理端的暫存還在）。

CREATE TABLE IF NOT EXISTS job_drive_parts (
    job_id text NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    relative_path text NOT NULL, -- 與 Core artifacts 相同的相對路徑，例如 page_0/text_layers/1.png
    drive_file_id text NOT NULL,
    content_type text,
    size_bytes bigint,
    synced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_job_drive_parts_job_id ON job_drive_parts(job_id);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pages_manifest jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS rebuilt_pptx_relative text;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS parts_backed_up_at timestamptz;
