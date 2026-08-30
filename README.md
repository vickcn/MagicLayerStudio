# MagicLayerStudio

`main.py` 是專案的正式入口。

這個工具會把 OCR 結果中的文字框抽出成獨立透明圖層，並輸出對應的 `layers.json`。預設會同時產生 debug 圖，方便檢查分離結果；大量批次處理時可以關掉。

## 使用方式

```bash
source ~/tchop/bin/activate
python main.py \
  --image samples/slide_002.png \
  --json output/slide_002_res.json \
  --output tmp/output_layers
```

關閉 debug 輸出：

```bash
python main.py \
  --image samples/slide_002.png \
  --json output/slide_002_res.json \
  --output tmp/output_layers \
  --no-debug
```

## 參數

- `--image`: 原始圖片
- `--json`: PaddleOCR 輸出的 JSON
- `--output`: 輸出資料夾，預設 `output_layers`
- `--min-score`: 最低信心分數，預設 `0.50`
- `--padding`: 文字框外擴像素，預設 `8`
- `--no-debug`: 關閉 debug 圖輸出

## 輸出

預設輸出如下：

```text
output/
├── layers.json
├── combined_text_mask.png
├── preview_layers.png
├── reconstructed_text.png
└── text_layers/
    ├── text_000_....png
    ├── text_001_....png
    └── ...
```

## 相容入口

`src/extract_text_layers.py` 保留為相容入口，內部會轉呼叫同一套 CLI 邏輯。新專案或手動執行時，請優先使用 `main.py`。
