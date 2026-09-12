# MagicLayerStudio

MagicLayerStudio 是一個簡報圖層分離與重組工具，能自動從簡報圖片或 PPTX 中抽離文字生成獨立透明前景圖層，並抹平背景生成乾淨底圖，最後重組回 PPTX 檔案。

`main.py` 是專案的正式主入口。

---

## 核心流程與參數隔離設計

本系統將**前景文字圖層擷取**與**背景修復抹平**的參數進行隔離控制，確保疊合時兼具高視覺質感的文字細節與乾淨無殘影的背景：

1. **前景文字圖層參數**：
   * `--pdf-dpi 120`：高解析度渲染，確保文字筆劃高頻細節不丟失、無嚴重鋸齒。
   * `-pd` / `--padding 8`：文字塊外擴像素（預設 `8`），確保完整的半透明字體羽化邊緣。
2. **背景修復抹平參數**：
   * `-dk` / `--dilate-kernel 3`：背景擦除的膨脹核大小（預設 `3`），僅在文字週邊做保守修補，避免背景人物或物件大面積模糊。
   * `-ir` / `--inpaint-radius 1`：OpenCV Inpainting 周邊參考半徑（預設 `1`）。
3. **自動重組疊合**：
   * 將高解析度的透明前景文字圖層與擦除乾淨的背景底圖，依據原始 OCR 座標自動重新疊合成全新的 `.pptx` 簡報。

---

## 環境準備

執行 Python 腳本與修復功能：
```bash
conda activate lama
```

PaddleOCR 自動交給 `padocr` 環境處理（無需手動切換）。

---

## 使用方式

詳細操作指南請參閱 [USAGE.md](file:///Users/kexuen/projects/MagicLayerStudio/USAGE.md)。

### 0. 網頁站台 (Web UI)

啟動 FastAPI Web 伺服器：
```bash
cp .env.example .env  # 本地預設 STUDIO_BACKEND=local
./scripts/start-studio-local.sh --reload
```
啟動後開啟瀏覽器存取 `http://localhost:8000/app/` 即可體驗視覺化上傳、單一物件圖層/文字模式切換與 PPTX 匯出功能。

### 0.1 Backend adapter 與 Vercel

Studio 的後端由 `STUDIO_BACKEND` 選擇：

- `local`（預設）：直接使用本 repo 的 `src.pipeline`，適合本地 conda `lama` 環境。
- `core_api`：透過 `MAGICLAYER_CORE_URL` 呼叫已部署的 MagicLayerCore，適合 Vercel。

Vercel 部署前，在 Vercel Project Settings → Environment Variables 設定：

```text
STUDIO_BACKEND=core_api
MAGICLAYER_CORE_URL=https://<magiclayer-core-api>
MAGICLAYER_CORE_TOKEN=<optional-bearer-token>
```

專案已包含 `api/index.py`、`vercel.json` 與根目錄 `requirements.txt`。本地可用
`./scripts/start-studio-vercel.sh` 對 Core API 模式做 smoke test；正式部署使用
`vercel` CLI 或連接 Git repository 即可。Vercel 端不會載入本地 OCR/影像 pipeline，避免把
重量級 conda 依賴帶進 Function bundle。

### 1. 處理簡報文件（PPTX / PDF / 多頁圖片）並自動重組 PPTX

```bash
conda run -n lama python main.py samples/Offering.pptx -o tmp/output_doc
```

自訂參數範例：
```bash
conda run -n lama python main.py samples/Offering.pptx \
  -o tmp/output_doc \
  --pdf-dpi 120 \
  -dk 31 \
  -pd 8
```

### 2. 處理單張圖片與已有 OCR JSON

```bash
conda run -n lama python main.py \
  --image samples/slide_002.png \
  --json output/slide_002_res.json \
  --output tmp/output_layers
```

關閉 debug 預覽圖輸出：
```bash
conda run -n lama python main.py samples/Offering.pptx -o tmp/output_doc --no-debug
```

---

## CLI 參數說明

- **文件與輸入輸出**：
  - `inputs`: 輸入檔案路徑（支援 `.pptx`, `.pdf`, `.png` 等）
  - `-o`, `--output`: 輸出資料夾，預設 `output_document`
  - `--pptx-output`: 自訂輸出的 PPTX 檔案路徑
  - `-nrb`, `--no-rebuild-pptx`: 停用自動重組 PPTX 功能

- **前景文字擷取**：
  - `--pdf-dpi`: 簡報渲染成 PDF/圖片的 DPI，預設 `120`
  - `-pd`, `--padding`: 文字切割外擴像素，預設 `8`
  - `-ms`, `--min-score`: OCR 最低信心分數過濾，預設 `0.50`

- **背景擦除修復**：
  - `-dk`, `--dilate-kernel`: 背景修復時的文字遮罩膨脹核大小，預設 `31`
  - `-ir`, `--inpaint-radius`: OpenCV 塗抹修復半徑，預設 `5`
  - `-ib`, `--inpaint-backend`: 背景修復後端 (`telea`, `sd`, `none`)，預設 `telea`
  - `-nh`, `--no-harmonize`: 停用背景邊緣諧調後處理

- **其他選項**：
  - `-nd`, `--no-debug`: 關閉 Debug 預覽圖與中間產物輸出

---

## 輸出結構

處理文件後的預設目錄結構：

```text
tmp/output_doc/
├── document.json               # 簡報各頁結構清單
├── Offering_rebuilt.pptx       # 最終疊合重組完成的 PPTX
├── page_001.zip                # 第 1 頁圖層壓縮包
├── page_001/
│   ├── background_telea.png   # 擦除文字後的乾淨背景底圖
│   ├── layers.json             # 文字圖層與座標描述
│   ├── objects.json            # 物件組合與位移描述
│   └── text_layers/            # 抽離出來的獨立透明前景文字圖層 (.png)
│       ├── text_000_....png
│       └── ...
└── ...
```

---

## 相容入口

`src/extract_text_layers.py` 保留為相容入口，內部會轉呼叫同一套 CLI 邏輯。執行正式流程時，請優先使用 `main.py` 或 `src/document_cli.py`。
