# ── Build Stage ──────────────────────────────────────────────────────────────
# MagicLayerStudio Web Backend — Cloud Run ready
#
# Build:
#   docker build -f web/Dockerfile -t magiclayerstudio-web .
#
# Run locally:
#   docker run -p 8080:8080 -v $(pwd)/tmp:/app/tmp magiclayerstudio-web
#
# NOTE: PaddleOCR 及 lama inpainting 需在 base image 中預裝，
#       或透過 conda run 子行程呼叫（預設行為）。
#       若要在 Cloud Run 完整執行，需使用含 conda 環境的 base image。

FROM continuumio/miniconda3:24.3.0-0 AS base

WORKDIR /app

# 複製 conda 環境設定（若有的話）
# COPY environment.yml .
# RUN conda env create -f environment.yml

# 安裝後端基礎套件（lama 環境的 FastAPI 相依）
COPY web/backend/requirements.txt /app/web/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/web/backend/requirements.txt

# 複製原始碼
COPY src/ /app/src/
COPY main.py /app/main.py
COPY web/ /app/web/

# 建立暫存目錄
RUN mkdir -p /app/tmp/web_jobs

# Cloud Run 使用 PORT 環境變數
ENV PORT=8080
ENV MAX_CONCURRENT_JOBS=2
ENV JOB_TTL_SECONDS=86400

EXPOSE 8080

CMD ["uvicorn", "web.backend.app:app", "--host", "0.0.0.0", "--port", "8080"]
