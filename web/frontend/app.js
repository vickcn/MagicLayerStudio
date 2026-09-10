/* app.js — MagicLayerStudio Frontend Interactive Editor Logic */
/* 純 Vanilla JS，不依賴第三方框架 */

const API = '';  // 後端同 origin

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  file: null,
  jobId: null,
  uploadMode: null, // local | gcs；由後端能力檢查決定
  capabilitiesReady: false,
  status: 'idle',  // idle | uploading | processing | done | error
  isBusy: false,
  pollFailures: 0,
  pages: [],
  selectedPageIndex: 0,
  selectedView: 'editor',  // editor | source | background | layer
  selectedLayerIndex: 0,
  selectedObjId: null,
  jobSize: null,
  
  // 自訂編輯資料：[pageIndex][objId] = { id, mode, text, x, y, width, height, deleted, style: {...} }
  customEdits: {},
  // 當前畫布的天然解析度
  canvasNaturalSize: { width: 1920, height: 1080 },
  // 是否有未儲存的變更
  isDirty: false,

  // 歷史記錄堆疊 (Undo / Redo)
  undoStack: [],
  redoStack: [],

  // 剪貼簿
  clipboard: null,
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const $uploadZone      = $('upload-zone');
const $fileInput       = $('file-input');
const $fileInfo        = $('file-info');
const $fileName        = $('file-name');
const $btnRemove       = $('btn-remove-file');
const $btnProcess      = $('btn-process');
const $progressWrap    = $('progress-wrap');
const $progressBar     = $('progress-bar');
const $statusText      = $('status-text');
const $pagesEmpty      = $('pages-empty');
const $pagesGrid       = $('pages-grid');
const $pageDetail      = $('page-detail');
const $pageTitle       = $('page-title');
const $badgeDraft      = $('badge-draft');

const $btnUndo         = $('btn-undo');
const $btnRedo         = $('btn-redo');
const $btnAddText      = $('btn-add-text');
const $btnSaveDraft    = $('btn-save-draft');
const $btnDiscardDraft = $('btn-discard-draft');

const $canvasContainer = $('canvas-container');
const $canvasStage     = $('canvas-stage');
const $mainImg         = $('main-img');
const $canvasOverlay   = $('canvas-overlay');
const $imgLoading      = $('img-loading');

const $layersSidebar   = $('layers-sidebar');
const $actionBar       = $('action-bar');
const $actionInfo      = $('action-info');
const $btnDownload     = $('btn-download');
const $btnReprocess    = $('btn-reprocess');
const $btnDeleteJob    = $('btn-delete-job');
const $paramsToggle    = $('params-toggle');
const $paramsBody      = $('params-body');
const $toastContainer  = $('toast-container');
const $headerStatusText = $('header-status-text');
const $pagesCount      = $('pages-count');
const $busyOverlay     = $('busy-overlay');
const $busyTitle       = $('busy-title');
const $busyMessage     = $('busy-message');
const $confirmModal    = $('confirm-modal');
const $confirmTitle    = $('confirm-title');
const $confirmMessage  = $('confirm-message');
const $confirmClose    = $('confirm-close');
const $confirmCancel   = $('confirm-cancel');
const $confirmSubmit   = $('confirm-submit');

// Inspector DOM
const $inspectorPanel   = $('inspector-panel');
const $inspectorEmpty   = $('inspector-empty');
const $inspectorBody    = $('inspector-body');
const $inspectorObjId   = $('inspector-obj-id');
const $modeImageBtn     = $('mode-image-btn');
const $modeWordartBtn   = $('mode-wordart-btn');
const $propText         = $('prop-text');
const $propFontName     = $('prop-font-name');
const $propFontSize     = $('prop-font-size');
const $propBold         = $('prop-bold');
const $propItalic       = $('prop-italic');
const $propAlignLeft    = $('prop-align-left');
const $propAlignCenter  = $('prop-align-center');
const $propAlignRight   = $('prop-align-right');
const $propColor        = $('prop-color');
const $propColorHex     = $('prop-color-hex');
const $propPosX         = $('prop-pos-x');
const $propPosY         = $('prop-pos-y');
const $propPosW         = $('prop-pos-w');
const $propPosH         = $('prop-pos-h');
const $btnCopyObj       = $('btn-copy-obj');
const $btnDeleteObj     = $('btn-delete-obj');

// ── Params ────────────────────────────────────────────────────────────────────
function getParams() {
  return {
    pdf_dpi:       parseInt($('p-pdf-dpi').value) || 120,
    padding:       parseInt($('p-padding').value) || 8,
    min_score:     parseFloat($('p-min-score').value) || 0.50,
    dilate_kernel: parseInt($('p-dilate-kernel').value) || 31,
    inpaint_radius:parseInt($('p-inpaint-radius').value) || 5,
    inpaint_backend: $('p-inpaint-backend').value,
    rebuild_pptx:  true,
  };
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast' + (type ? ` ${type}` : '');
  el.textContent = msg;
  $toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 2800);
}

function previewText(text, limit = 42) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 1)}…`;
}

function setBusy(isBusy, title = '處理中', message = '正在準備作業，請稍候。') {
  state.isBusy = isBusy;
  document.body.classList.toggle('is-busy', isBusy);
  document.body.setAttribute('aria-busy', isBusy ? 'true' : 'false');
  $busyTitle.textContent = title;
  $busyMessage.textContent = message;
  $busyOverlay.classList.toggle('hidden', !isBusy);
  syncDisabledControls();
}

function syncDisabledControls() {
  const busy = state.isBusy;
  $fileInput.disabled = busy;
  $btnRemove.disabled = busy || !state.file;
  $btnProcess.disabled = busy || !state.file || !state.capabilitiesReady;
  $btnReprocess.disabled = busy || !state.file;
  $btnDownload.disabled = busy || !state.jobId;
  $btnDeleteJob.disabled = busy || !state.jobId;
}

function confirmAction({ title, message, confirmLabel = '確認', danger = false }) {
  return new Promise((resolve) => {
    $confirmTitle.textContent = title;
    $confirmMessage.textContent = message;
    $confirmSubmit.textContent = confirmLabel;
    $confirmSubmit.classList.toggle('btn-accent', danger);
    $confirmSubmit.classList.toggle('btn-primary', !danger);
    $confirmModal.classList.remove('hidden');
    $confirmCancel.focus();

    const cleanup = (result) => {
      $confirmModal.classList.add('hidden');
      $confirmSubmit.classList.remove('btn-primary');
      $confirmSubmit.classList.add('btn-accent');
      $confirmSubmit.removeEventListener('click', onConfirm);
      $confirmCancel.removeEventListener('click', onCancel);
      $confirmClose.removeEventListener('click', onCancel);
      $confirmModal.removeEventListener('click', onBackdrop);
      window.removeEventListener('keydown', onKey);
      resolve(result);
    };

    const onConfirm = () => cleanup(true);
    const onCancel = () => cleanup(false);
    const onBackdrop = (event) => {
      if (event.target === $confirmModal) cleanup(false);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') cleanup(false);
    };

    $confirmSubmit.addEventListener('click', onConfirm);
    $confirmCancel.addEventListener('click', onCancel);
    $confirmClose.addEventListener('click', onCancel);
    $confirmModal.addEventListener('click', onBackdrop);
    window.addEventListener('keydown', onKey);
  });
}

// ── Upload zone ───────────────────────────────────────────────────────────────
$uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  $uploadZone.classList.add('drag-over');
});
$uploadZone.addEventListener('dragleave', () => $uploadZone.classList.remove('drag-over'));
$uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  $uploadZone.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});
$fileInput.addEventListener('change', () => {
  if ($fileInput.files[0]) setFile($fileInput.files[0]);
});
$btnRemove.addEventListener('click', (e) => {
  e.stopPropagation();
  clearFile();
});

const ALLOWED = ['.pptx', '.pdf', '.png', '.jpg', '.jpeg'];
function setFile(f) {
  if (state.isBusy) return;
  const ext = '.' + f.name.split('.').pop().toLowerCase();
  if (!ALLOWED.includes(ext)) {
    toast(`不支援 ${ext} 格式，請上傳 ${ALLOWED.join(' / ')}`, 'error');
    return;
  }
  state.file = f;
  $fileName.textContent = f.name;
  $fileInfo.classList.remove('hidden');
  resetResults();
  syncDisabledControls();
}

function clearFile() {
  if (state.isBusy) return;
  state.file = null;
  $fileInput.value = '';
  $fileInfo.classList.add('hidden');
  resetResults();
  syncDisabledControls();
}

// ── Process ───────────────────────────────────────────────────────────────────
$btnProcess.addEventListener('click', startProcess);
$btnReprocess.addEventListener('click', startProcess);

async function startProcess() {
  if (!state.file || state.isBusy) return;

  resetResults();
  setStatus('uploading');
  setBusy(true, '正在上傳檔案', '檔案上傳後會立即開始分析圖層。');

  try {
    const params = getParams();
    let job_id;
    if (state.uploadMode === 'gcs') {
      const prepareRes = await fetch(`${API}/api/upload/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: state.file.name,
          content_type: state.file.type || 'application/octet-stream',
          size: state.file.size,
        }),
      });
      if (!prepareRes.ok) throw new Error('無法準備安全上傳');
      const prepared = await prepareRes.json();

      const putRes = await fetch(prepared.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': prepared.content_type },
        body: state.file,
      });
      if (!putRes.ok) throw new Error('檔案直傳暫存區失敗');

      const completeRes = await fetch(`${API}/api/upload/${encodeURIComponent(prepared.upload_id)}/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ options: params, filename: state.file.name, size: state.file.size }),
      });
      if (!completeRes.ok) throw new Error('Core 未能確認上傳檔案');
      ({ job_id } = await completeRes.json());
    } else {
      const fd = new FormData();
      fd.append('file', state.file);
      const upRes = await fetch(`${API}/api/upload`, { method: 'POST', body: fd });
      if (!upRes.ok) {
        const err = await upRes.json().catch(() => ({ detail: '上傳失敗' }));
        throw new Error(err.detail || '上傳失敗');
      }
      ({ job_id } = await upRes.json());
    }
    state.jobId = job_id;

    setStatus('processing');
    setBusy(true, '正在分離圖層', '大型簡報可能需要幾分鐘，完成後會自動顯示頁面縮圖。');
    if (state.uploadMode !== 'gcs') {
      const qs = new URLSearchParams(params).toString();
      const procRes = await fetch(`${API}/api/process/${job_id}?${qs}`, { method: 'POST' });
      if (!procRes.ok) {
        const err = await procRes.json().catch(() => ({ detail: '啟動失敗' }));
        throw new Error(err.detail || '啟動失敗');
      }
    }

    pollStatus(job_id);
  } catch (e) {
    setStatus('error', e.message);
    setBusy(false);
    toast(e.message, 'error');
  }
}

let _pollTimer = null;
let _pollInFlight = false;
const QUEUE_POLL_OFFLINE_THRESHOLD = 1;
const QUEUE_POLL_MAX_FAILURES = 2;
const QUEUE_POLL_INTERVAL_MS = 1500;

function stopPolling() {
  if (_pollTimer) clearInterval(_pollTimer);
  _pollTimer = null;
  _pollInFlight = false;
}

function pollStatus(job_id) {
  stopPolling();
  _pollTimer = setInterval(async () => {
    if (_pollInFlight) return;
    _pollInFlight = true;
    try {
      const r = await fetch(`${API}/api/jobs/${job_id}/status`);
      if (!r.ok) {
        const err = new Error(`HTTP ${r.status}`);
        err.stopPolling = r.status === 401 || r.status === 404;
        throw err;
      }
      const data = await r.json();
      if (state.pollFailures > 0) {
        toast('已重新連上服務，繼續更新處理狀態', 'success');
      }
      state.pollFailures = 0;
      $statusText.textContent = data.progress || '處理中…';

      if (data.status === 'done') {
        stopPolling();
        await loadResult(job_id);
      } else if (data.status === 'error') {
        stopPolling();
        setStatus('error', data.progress || '處理失敗');
        toast(data.progress || '處理失敗', 'error');
      }
    } catch (err) {
      if (err.stopPolling) {
        stopPolling();
        const message = err.message.includes('401')
          ? '工作驗證已失效，請重新上傳。'
          : '找不到這個工作，請重新上傳。';
        setStatus('error', message);
        toast(message, 'error');
        return;
      }
      state.pollFailures += 1;
      console.error('status polling failed', err);
      if (state.pollFailures >= QUEUE_POLL_OFFLINE_THRESHOLD) {
        $statusText.textContent = `服務連線中斷，正在重試（${state.pollFailures}/${QUEUE_POLL_MAX_FAILURES}）。`;
        $statusText.classList.add('error');
        setBusy(false);
      }
      if (state.pollFailures >= QUEUE_POLL_MAX_FAILURES) {
        stopPolling();
        const message = '服務暫時無法連線，已停止重試，請稍後再試。';
        setStatus('error', message);
        toast(message, 'error');
      }
    } finally {
      _pollInFlight = false;
    }
  }, QUEUE_POLL_INTERVAL_MS);
}

async function loadResult(job_id) {
  try {
    const r = await fetch(`${API}/api/jobs/${job_id}/result`);
    if (!r.ok) throw new Error('無法取得結果');
    const data = await r.json();
    state.pages = data.pages || [];
    state.rebuiltPptx = data.rebuilt_pptx;
    state.jobSize = data.size_mb || null;
    state.customEdits = data.custom_edits || {};
    state.undoStack = [];
    state.redoStack = [];
    setStatus('done');
    renderPages();
    if (state.pages.length > 0) selectPage(0);
  } catch (err) {
    console.error('load result failed', err);
    setStatus('error', err.message || '無法取得結果');
    toast(err.message || '無法取得結果', 'error');
  } finally {
    setBusy(false);
  }
}

// ── Status helpers ────────────────────────────────────────────────────────────
function setStatus(s, msg) {
  state.status = s;
  document.body.dataset.status = s;
  $statusText.className = 'status-text';
  $progressWrap.classList.remove('hidden');
  $progressBar.classList.remove('indeterminate');

  if (s === 'idle') {
    $progressWrap.classList.add('hidden');
    $statusText.textContent = '';
    $btnProcess.querySelector('.spinner')?.remove();
    setBusy(false);
  } else if (s === 'uploading') {
    $progressBar.style.width = '15%';
    $progressBar.classList.add('indeterminate');
    $statusText.textContent = '上傳中…';
    ensureSpinner($btnProcess);
  } else if (s === 'processing') {
    $progressBar.classList.add('indeterminate');
    $statusText.textContent = '分析與分離圖層中…';
    ensureSpinner($btnProcess);
  } else if (s === 'done') {
    $progressBar.classList.remove('indeterminate');
    $progressBar.style.width = '100%';
    $statusText.textContent = `完成，共 ${state.pages.length} 頁`;
    $statusText.classList.add('success');
    removeSpinner($btnProcess);
    $actionBar.classList.remove('hidden');
    updateActionBar();
    toast('圖層分離完成', 'success');
    setBusy(false);
  } else if (s === 'error') {
    $progressBar.classList.remove('indeterminate');
    $progressBar.style.width = '0%';
    $statusText.textContent = msg || '發生錯誤';
    $statusText.classList.add('error');
    removeSpinner($btnProcess);
    setBusy(false);
  }
  $headerStatusText.textContent = {
    idle: '本機工作台',
    uploading: '上傳中',
    processing: '處理中',
    done: '處理完成',
    error: '需要處理',
  }[s] || '本機工作台';
  syncDisabledControls();
}

function ensureSpinner(btn) {
  if (!btn.querySelector('.spinner')) {
    const sp = document.createElement('span');
    sp.className = 'spinner';
    btn.prepend(sp);
  }
}
function removeSpinner(btn) {
  btn.querySelector('.spinner')?.remove();
}

function resetResults() {
  state.pages = [];
  state.jobId = null;
  state.customEdits = {};
  state.isDirty = false;
  state.selectedObjId = null;
  state.undoStack = [];
  state.redoStack = [];
  state.pollFailures = 0;
  $pagesEmpty.classList.remove('hidden');
  $pagesGrid.classList.add('hidden');
  $pagesGrid.innerHTML = '';
  $pagesCount.textContent = '0 頁';
  $pageDetail.classList.add('hidden');
  $actionBar.classList.add('hidden');
  stopPolling();
  setStatus('idle');
  updateDraftControls();
}

function getPageAssetUrl(pageIndex, field, assetIndex = 0) {
  const page = state.pages[pageIndex] || {};
  const value = field === 'layer_files' ? page.layer_files?.[assetIndex] : page[field];
  if (typeof value === 'string' && /^https?:\/\//i.test(value)) return value;

  if (field === 'source_image') {
    return `${API}/api/jobs/${state.jobId}/pages/${pageIndex}/source`;
  }
  if (field === 'background') {
    return `${API}/api/jobs/${state.jobId}/pages/${pageIndex}/background`;
  }
  if (field === 'layer_files') {
    return `${API}/api/jobs/${state.jobId}/pages/${pageIndex}/layers/${assetIndex}`;
  }
  return '';
}

// ── Pages grid ────────────────────────────────────────────────────────────────
function renderPages() {
  $pagesEmpty.classList.add('hidden');
  $pagesGrid.classList.remove('hidden');
  $pagesGrid.innerHTML = '';
  $pagesCount.textContent = `${state.pages.length} 頁`;

  state.pages.forEach((page, i) => {
    const card = document.createElement('div');
    card.className = 'page-card';
    card.dataset.index = i;
    card.innerHTML = `
      <div class="thumb-wrap">
        <img src="${getPageAssetUrl(i, 'source_image')}"
             alt="第 ${i+1} 頁縮圖" loading="lazy">
        <span class="layer-count-badge">${page.layer_count} 圖層</span>
      </div>
      <div class="card-footer">
        <span class="page-label">第 ${i+1} 頁</span>
        <span class="badge badge-gray">${page.layer_count} 層</span>
      </div>
    `;
    card.addEventListener('click', () => selectPage(i));
    $pagesGrid.appendChild(card);
  });
}

function selectPage(index) {
  state.selectedPageIndex = index;
  state.selectedView = 'editor';
  state.selectedLayerIndex = 0;
  state.selectedObjId = null;

  document.querySelectorAll('.page-card').forEach((c, i) => {
    c.classList.toggle('active', i === index);
  });

  const page = state.pages[index];
  $pageTitle.textContent = `第 ${index + 1} 頁 — ${page.layer_count} 個文字圖層`;
  $pageDetail.classList.remove('hidden');

  // 初始化該頁的 customEdits（若尚未存在）
  initPageEdits(index);

  updateViewTabs();
  closeInspector();
  renderSidebarList(index);
  loadCanvasView(state.selectedView, index);
  updateDraftControls();
}

// ── Custom edits state initialization ─────────────────────────────────────────
function initPageEdits(pIdx) {
  const pStr = String(pIdx);
  if (!state.customEdits[pStr]) {
    state.customEdits[pStr] = {};
  }
  const page = state.pages[pIdx];
  if (!page) return;

  const pageEdits = state.customEdits[pStr];
  (page.layers || []).forEach((layer) => {
    const lid = layer.id;
    if (!pageEdits[lid]) {
      const style = layer.style_hint || {};
      const rgb = style.dominant_color_rgb || [255, 255, 255];
      const hex = rgbToHex(rgb[0], rgb[1], rgb[2]);
      pageEdits[lid] = {
        id: lid,
        mode: 'image_layer',
        text: layer.text || '',
        x: layer.x || 0,
        y: layer.y || 0,
        width: layer.width || 100,
        height: layer.height || 40,
        deleted: false,
        style: {
          font_name: style.font_name_hint || 'Noto Sans TC',
          font_size_pt: Math.round(style.estimated_font_size_pt || 24),
          bold: Boolean(style.likely_bold),
          italic: false,
          align: 'center',
          color_rgb: rgb,
          color_hex: hex,
        }
      };
    }
  });
}

function getObjectEdit(pIdx, objId) {
  const pStr = String(pIdx);
  const edit = state.customEdits[pStr]?.[objId];
  if (edit && !edit.deleted) return edit;
  return null;
}

function getActivePageEdits(pIdx) {
  const pStr = String(pIdx);
  const edits = state.customEdits[pStr] || {};
  const list = [];
  for (const [id, item] of Object.entries(edits)) {
    if (item && !item.deleted) {
      list.push(item);
    }
  }
  return list;
}

// ── View tabs ─────────────────────────────────────────────────────────────────
document.querySelectorAll('.view-tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    const v = tab.dataset.view;
    if (v === 'layer' && state.pages[state.selectedPageIndex]?.layer_count === 0) {
      toast('此頁沒有文字圖層', '');
      return;
    }
    state.selectedView = v;
    updateViewTabs();
    loadCanvasView(v, state.selectedPageIndex, state.selectedLayerIndex);
  });
});

function updateViewTabs() {
  document.querySelectorAll('.view-tab').forEach((t) => {
    t.classList.toggle('active', t.dataset.view === state.selectedView);
  });
}

// ── Canvas View Loader ────────────────────────────────────────────────────────
function loadCanvasView(view, pageIndex, layerIndex = 0) {
  $mainImg.style.opacity = '0';
  $imgLoading.classList.remove('hidden');
  $imgLoading.textContent = '載入預覽中…';
  $canvasOverlay.innerHTML = '';

  let bgUrl = '';
  if (view === 'editor' || view === 'background') {
    bgUrl = getPageAssetUrl(pageIndex, 'background');
  } else if (view === 'source') {
    bgUrl = getPageAssetUrl(pageIndex, 'source_image');
  } else if (view === 'layer') {
    bgUrl = getPageAssetUrl(pageIndex, 'layer_files', layerIndex);
  }

  const tempImg = new Image();
  tempImg.onload = () => {
    $mainImg.src = tempImg.src;
    $mainImg.style.opacity = '1';
    $imgLoading.classList.add('hidden');

    state.canvasNaturalSize = {
      width: tempImg.naturalWidth || 1920,
      height: tempImg.naturalHeight || 1080,
    };

    $canvasContainer.style.background = view === 'layer'
      ? 'repeating-conic-gradient(#555 0% 25%, #333 0% 50%) 0 0 / 20px 20px'
      : '#1c1c1e';

    if (view === 'editor') {
      renderInteractiveOverlay(pageIndex);
    }
  };
  tempImg.onerror = () => {
    $imgLoading.textContent = '預覽載入失敗，請切換其他檢視或重新處理。';
    $mainImg.style.opacity = '0';
    console.error('canvas image load failed', bgUrl);
  };
  tempImg.src = bgUrl;
}

// ── Render Interactive Overlay ────────────────────────────────────────────────
function renderInteractiveOverlay(pageIndex) {
  $canvasOverlay.innerHTML = '';
  $canvasOverlay.onclick = (e) => {
    if (e.target === $canvasOverlay) deselectObject();
  };
  const activeItems = getActivePageEdits(pageIndex);

  const natW = state.canvasNaturalSize.width;
  const natH = state.canvasNaturalSize.height;

  activeItems.forEach((edit) => {
    const item = document.createElement('div');
    item.className = 'canvas-item' + (state.selectedObjId === edit.id ? ' selected' : '');
    item.id = `canvas-item-${edit.id}`;
    item.dataset.id = edit.id;

    updateCanvasItemStyle(item, edit, natW, natH);
    renderItemContent(item, edit, pageIndex);
    attachDragAndSelect(item, edit.id, pageIndex);

    $canvasOverlay.appendChild(item);
  });
}

function updateCanvasItemStyle(el, edit, natW, natH) {
  const leftPct = (edit.x / natW) * 100;
  const topPct = (edit.y / natH) * 100;
  const widthPct = (edit.width / natW) * 100;
  const heightPct = (edit.height / natH) * 100;

  el.style.left = `${leftPct}%`;
  el.style.top = `${topPct}%`;
  el.style.width = `${widthPct}%`;
  el.style.height = `${heightPct}%`;
}

function renderItemContent(itemEl, edit, pageIndex) {
  itemEl.innerHTML = '';
  const isCustomNew = edit.id.startsWith('custom_text_');

  if (edit.mode === 'image_layer' && !isCustomNew) {
    const img = document.createElement('img');
    img.className = 'canvas-item-img';
    const lIdx = (state.pages[pageIndex]?.layers || []).findIndex(l => l.id === edit.id);
    img.src = getPageAssetUrl(pageIndex, 'layer_files', lIdx >= 0 ? lIdx : 0);
    img.alt = edit.text || '文字圖層';
    itemEl.appendChild(img);
  } else {
    // wordart 模式
    const wordart = document.createElement('div');
    wordart.className = 'wordart-preview';
    wordart.textContent = edit.text;

    const s = edit.style || {};
    wordart.style.fontFamily = `"${s.font_name}", "Noto Sans TC", sans-serif`;
    wordart.style.fontWeight = s.bold ? '700' : '400';
    wordart.style.fontStyle = s.italic ? 'italic' : 'normal';
    wordart.style.color = s.color_hex || '#FFFFFF';
    wordart.style.textAlign = s.align || 'center';
    wordart.style.justifyContent = s.align === 'left' ? 'flex-start' : (s.align === 'right' ? 'flex-end' : 'center');
    
    const stageH = $canvasStage.clientHeight || 480;
    const scaleRatio = stageH / state.canvasNaturalSize.height;
    const scaledPx = Math.max(10, Math.round((s.font_size_pt * 1.333) * scaleRatio));
    wordart.style.fontSize = `${scaledPx}px`;

    itemEl.appendChild(wordart);
  }
}

// ── Drag & Select Handler ─────────────────────────────────────────────────────
function attachDragAndSelect(el, objId, pageIndex) {
  el.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    selectObject(objId);

    const edit = getObjectEdit(pageIndex, objId);
    if (!edit) return;

    const stageRect = $canvasStage.getBoundingClientRect();
    const natW = state.canvasNaturalSize.width;
    const natH = state.canvasNaturalSize.height;

    const startMouseX = e.clientX;
    const startMouseY = e.clientY;
    const startObjX = edit.x;
    const startObjY = edit.y;

    let hasMoved = false;

    function onMouseMove(moveEvent) {
      const dxPx = moveEvent.clientX - startMouseX;
      const dyPx = moveEvent.clientY - startMouseY;

      if (!hasMoved && (Math.abs(dxPx) > 2 || Math.abs(dyPx) > 2)) {
        hasMoved = true;
        pushUndo();
      }

      const scaleX = natW / stageRect.width;
      const scaleY = natH / stageRect.height;

      const newX = Math.round(startObjX + dxPx * scaleX);
      const newY = Math.round(startObjY + dyPx * scaleY);

      edit.x = Math.max(0, Math.min(natW - edit.width, newX));
      edit.y = Math.max(0, Math.min(natH - edit.height, newY));

      updateCanvasItemStyle(el, edit, natW, natH);
      updateInspectorPosition(edit);
      markDirty();
    }

    function onMouseUp() {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  });
}

function selectObject(objId) {
  state.selectedObjId = objId;

  document.querySelectorAll('.canvas-item').forEach((item) => {
    item.classList.toggle('selected', item.dataset.id === objId);
  });

  document.querySelectorAll('.layer-card-item').forEach((card) => {
    card.classList.toggle('active', card.dataset.id === objId);
  });

  openInspector(objId);
}

function deselectObject() {
  state.selectedObjId = null;
  document.querySelectorAll('.canvas-item').forEach((item) => {
    item.classList.remove('selected');
  });
  document.querySelectorAll('.layer-card-item').forEach((card) => {
    card.classList.remove('active');
  });
  closeInspector();
}

// ── Inspector Panel Logic ─────────────────────────────────────────────────────
function openInspector(objId) {
  const edit = getObjectEdit(state.selectedPageIndex, objId);
  if (!edit) { closeInspector(); return; }

  $inspectorEmpty.classList.add('hidden');
  $inspectorBody.classList.remove('hidden');
  $inspectorObjId.textContent = objId.startsWith('custom_text_') ? '自訂文字方塊' : objId;

  // 模式按鈕狀態
  $modeImageBtn.classList.toggle('active', edit.mode === 'image_layer');
  $modeWordartBtn.classList.toggle('active', edit.mode === 'wordart');

  // 若為使用者自訂新增的方塊，停用透明圖層模式（因為沒有原始圖片）
  const isCustomNew = edit.id.startsWith('custom_text_');
  $modeImageBtn.disabled = isCustomNew;
  $modeImageBtn.title = isCustomNew ? '新創文字物件僅支援文字藝術師' : '';

  // 文字內容
  $propText.value = edit.text || '';

  // 樣式
  const s = edit.style || {};
  $propFontName.value = s.font_name || 'Noto Sans TC';
  $propFontSize.value = s.font_size_pt || 24;
  $propBold.classList.toggle('active', Boolean(s.bold));
  $propItalic.classList.toggle('active', Boolean(s.italic));

  $propAlignLeft.classList.toggle('active', s.align === 'left');
  $propAlignCenter.classList.toggle('active', s.align === 'center' || !s.align);
  $propAlignRight.classList.toggle('active', s.align === 'right');

  $propColor.value = s.color_hex || '#ffffff';
  $propColorHex.value = (s.color_hex || '#FFFFFF').toUpperCase();

  // 座標
  updateInspectorPosition(edit);
}

function updateInspectorPosition(edit) {
  $propPosX.value = edit.x;
  $propPosY.value = edit.y;
  $propPosW.value = edit.width;
  $propPosH.value = edit.height;
}

function closeInspector() {
  $inspectorEmpty.classList.remove('hidden');
  $inspectorBody.classList.add('hidden');
  $inspectorObjId.textContent = '—';
}

// ── Inspector Event Bindings ──────────────────────────────────────────────────
$modeImageBtn.addEventListener('click', () => setMode('image_layer'));
$modeWordartBtn.addEventListener('click', () => setMode('wordart'));

function setMode(mode) {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  pushUndo();
  edit.mode = mode;
  $modeImageBtn.classList.toggle('active', mode === 'image_layer');
  $modeWordartBtn.classList.toggle('active', mode === 'wordart');

  refreshSelectedItemDOM();
  renderSidebarList(state.selectedPageIndex);
  markDirty();
}

$propText.addEventListener('input', (e) => {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  edit.text = e.target.value;
  refreshSelectedItemDOM();
  renderSidebarList(state.selectedPageIndex);
  markDirty();
});

$propFontName.addEventListener('change', (e) => {
  pushUndo();
  updateCurrentStyle({ font_name: e.target.value });
});

$propFontSize.addEventListener('input', (e) => {
  const val = parseFloat(e.target.value) || 24;
  updateCurrentStyle({ font_size_pt: val });
});

$propBold.addEventListener('click', () => {
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;
  pushUndo();
  const next = !edit.style.bold;
  $propBold.classList.toggle('active', next);
  updateCurrentStyle({ bold: next });
});

$propItalic.addEventListener('click', () => {
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;
  pushUndo();
  const next = !edit.style.italic;
  $propItalic.classList.toggle('active', next);
  updateCurrentStyle({ italic: next });
});

$propAlignLeft.addEventListener('click', () => { pushUndo(); setAlign('left'); });
$propAlignCenter.addEventListener('click', () => { pushUndo(); setAlign('center'); });
$propAlignRight.addEventListener('click', () => { pushUndo(); setAlign('right'); });

function setAlign(align) {
  $propAlignLeft.classList.toggle('active', align === 'left');
  $propAlignCenter.classList.toggle('active', align === 'center');
  $propAlignRight.classList.toggle('active', align === 'right');
  updateCurrentStyle({ align });
}

$propColor.addEventListener('input', (e) => {
  const hex = e.target.value.toUpperCase();
  $propColorHex.value = hex;
  const rgb = hexToRgb(hex);
  updateCurrentStyle({ color_hex: hex, color_rgb: rgb });
});

$propColorHex.addEventListener('change', (e) => {
  let hex = e.target.value.trim();
  if (!hex.startsWith('#')) hex = '#' + hex;
  if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
    pushUndo();
    $propColor.value = hex;
    const rgb = hexToRgb(hex);
    updateCurrentStyle({ color_hex: hex.toUpperCase(), color_rgb: rgb });
  }
});

[$propPosX, $propPosY, $propPosW, $propPosH].forEach((input) => {
  input.addEventListener('change', () => {
    if (!state.selectedObjId) return;
    const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
    if (!edit) return;

    pushUndo();
    edit.x = parseInt($propPosX.value) || edit.x;
    edit.y = parseInt($propPosY.value) || edit.y;
    edit.width = parseInt($propPosW.value) || edit.width;
    edit.height = parseInt($propPosH.value) || edit.height;

    const el = document.getElementById(`canvas-item-${edit.id}`);
    if (el) {
      updateCanvasItemStyle(el, edit, state.canvasNaturalSize.width, state.canvasNaturalSize.height);
    }
    markDirty();
  });
});

function updateCurrentStyle(partial) {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  edit.style = { ...edit.style, ...partial };
  refreshSelectedItemDOM();
  markDirty();
}

function refreshSelectedItemDOM() {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  const el = document.getElementById(`canvas-item-${state.selectedObjId}`);
  if (el && edit) {
    renderItemContent(el, edit, state.selectedPageIndex);
  }
}

// ── Object Actions: Add / Copy / Paste / Delete ───────────────────────────────
$btnAddText.addEventListener('click', addNewTextObject);
$btnCopyObj.addEventListener('click', copySelectedObject);
$btnDeleteObj.addEventListener('click', deleteSelectedObject);

function addNewTextObject() {
  const pIdx = state.selectedPageIndex;
  const pStr = String(pIdx);
  if (!state.customEdits[pStr]) state.customEdits[pStr] = {};

  pushUndo();

  const newId = `custom_text_${Date.now().toString(36)}`;
  const natW = state.canvasNaturalSize.width || 1920;
  const natH = state.canvasNaturalSize.height || 1080;

  const w = 450;
  const h = 100;
  const x = Math.round((natW - w) / 2);
  const y = Math.round((natH - h) / 2);

  const newObj = {
    id: newId,
    mode: 'wordart',
    text: '點擊編輯文字',
    x: x,
    y: y,
    width: w,
    height: h,
    deleted: false,
    style: {
      font_name: 'Noto Sans TC',
      font_size_pt: 32,
      bold: true,
      italic: false,
      align: 'center',
      color_rgb: [255, 215, 0],
      color_hex: '#FFD700',
    }
  };

  state.customEdits[pStr][newId] = newObj;

  renderInteractiveOverlay(pIdx);
  renderSidebarList(pIdx);
  selectObject(newId);
  markDirty();
  toast('已新增文字方塊', 'success');
}

function copySelectedObject() {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  state.clipboard = JSON.parse(JSON.stringify(edit));

  const el = document.getElementById(`canvas-item-${state.selectedObjId}`);
  if (el) {
    el.classList.remove('pulse-copy');
    void el.offsetWidth;
    el.classList.add('pulse-copy');
    setTimeout(() => el.classList.remove('pulse-copy'), 380);
  }

  const label = previewText(edit.text || edit.id, 14);
  toast(`已複製物件「${label}」`, 'success');
}

function pasteObject() {
  if (!state.clipboard) {
    toast('剪貼簿是空的', '');
    return;
  }

  const pIdx = state.selectedPageIndex;
  const pStr = String(pIdx);
  if (!state.customEdits[pStr]) state.customEdits[pStr] = {};

  pushUndo();

  const newId = `custom_text_${Date.now().toString(36)}`;
  const natW = state.canvasNaturalSize.width || 1920;
  const natH = state.canvasNaturalSize.height || 1080;

  const copy = JSON.parse(JSON.stringify(state.clipboard));
  copy.id = newId;
  copy.mode = 'wordart'; // 貼上均為文字方塊
  const offset = 30;
  copy.x = Math.max(0, Math.min(natW - copy.width, copy.x + offset));
  copy.y = Math.max(0, Math.min(natH - copy.height, copy.y + offset));
  copy.deleted = false;

  state.customEdits[pStr][newId] = copy;

  renderInteractiveOverlay(pIdx);
  renderSidebarList(pIdx);
  selectObject(newId);
  markDirty();

  const el = document.getElementById(`canvas-item-${newId}`);
  if (el) {
    el.classList.add('pop-paste');
    setTimeout(() => el.classList.remove('pop-paste'), 300);
  }

  const label = previewText(copy.text || '文字物件', 14);
  toast(`已貼上文字物件「${label}」`, 'success');
}

function deleteSelectedObject() {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  const label = previewText(edit.text || edit.id, 14);
  pushUndo();

  const pIdx = state.selectedPageIndex;

  edit.deleted = true;
  deselectObject();

  renderInteractiveOverlay(pIdx);
  renderSidebarList(pIdx);
  markDirty();
  toast(`已刪除物件「${label}」`, '');
}

function moveSelectedObject(dx, dy) {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  pushUndo();
  const natW = state.canvasNaturalSize.width || 1920;
  const natH = state.canvasNaturalSize.height || 1080;

  edit.x = Math.max(0, Math.min(natW - edit.width, edit.x + dx));
  edit.y = Math.max(0, Math.min(natH - edit.height, edit.y + dy));

  const el = document.getElementById(`canvas-item-${edit.id}`);
  if (el) {
    updateCanvasItemStyle(el, edit, natW, natH);
  }
  updateInspectorPosition(edit);
  markDirty();
}

// ── Undo / Redo History Stack ─────────────────────────────────────────────────
function pushUndo() {
  const snapshot = JSON.stringify(state.customEdits);
  state.undoStack.push(snapshot);
  if (state.undoStack.length > 30) state.undoStack.shift();
  state.redoStack = []; // 清空 redo
  updateUndoRedoButtons();
}

function undo() {
  if (state.undoStack.length === 0) return;
  const current = JSON.stringify(state.customEdits);
  state.redoStack.push(current);

  const prev = state.undoStack.pop();
  state.customEdits = JSON.parse(prev);

  restoreStateAfterHistoryChange();
  toast('已復原', '');
}

function redo() {
  if (state.redoStack.length === 0) return;
  const current = JSON.stringify(state.customEdits);
  state.undoStack.push(current);

  const next = state.redoStack.pop();
  state.customEdits = JSON.parse(next);

  restoreStateAfterHistoryChange();
  toast('已重做', '');
}

function restoreStateAfterHistoryChange() {
  const pIdx = state.selectedPageIndex;
  renderInteractiveOverlay(pIdx);
  renderSidebarList(pIdx);
  if (state.selectedObjId) {
    const edit = getObjectEdit(pIdx, state.selectedObjId);
    if (edit) openInspector(state.selectedObjId);
    else closeInspector();
  } else {
    closeInspector();
  }
  markDirty();
  updateUndoRedoButtons();
}

function updateUndoRedoButtons() {
  $btnUndo.disabled = state.undoStack.length === 0;
  $btnRedo.disabled = state.redoStack.length === 0;
}

$btnUndo.addEventListener('click', undo);
$btnRedo.addEventListener('click', redo);

// ── Global Keyboard Shortcuts ─────────────────────────────────────────────────
window.addEventListener('keydown', (e) => {
  const activeEl = document.activeElement;
  const isTyping = activeEl && (
    activeEl.tagName === 'INPUT' ||
    activeEl.tagName === 'TEXTAREA' ||
    activeEl.tagName === 'SELECT' ||
    activeEl.isContentEditable ||
    Boolean(activeEl.closest('.modal-backdrop'))
  );
  const isCtrl = e.ctrlKey || e.metaKey;

  // Esc: 取消選取
  if (e.key === 'Escape') {
    if (state.selectedObjId && !isTyping) {
      e.preventDefault();
      deselectObject();
      return;
    }
  }

  // 若處於文字輸入框，不攔截編輯畫布快捷鍵
  if (isTyping) return;

  // Ctrl+Z: Undo
  if (isCtrl && e.code === 'KeyZ' && !e.shiftKey) {
    e.preventDefault();
    undo();
    return;
  }

  // Ctrl+Shift+Z or Ctrl+Y: Redo
  if ((isCtrl && e.code === 'KeyZ' && e.shiftKey) || (isCtrl && e.code === 'KeyY')) {
    e.preventDefault();
    redo();
    return;
  }

  // Ctrl+C: Copy
  if (isCtrl && e.code === 'KeyC') {
    e.preventDefault();
    copySelectedObject();
    return;
  }

  // Ctrl+V: Paste
  if (isCtrl && e.code === 'KeyV') {
    e.preventDefault();
    pasteObject();
    return;
  }

  // Ctrl+S: Save Draft
  if (isCtrl && e.code === 'KeyS') {
    e.preventDefault();
    if (state.isDirty) saveCustomEdits();
    return;
  }

  // Delete / Backspace: Delete selected object
  if ((e.key === 'Delete' || e.key === 'Backspace') && state.selectedObjId) {
    e.preventDefault();
    deleteSelectedObject();
    return;
  }

  // 方向鍵: 微調物件位置 (Shift 為 10px)
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) && state.selectedObjId) {
    e.preventDefault();
    const step = e.shiftKey ? 10 : 1;
    let dx = 0, dy = 0;
    if (e.key === 'ArrowLeft') dx = -step;
    if (e.key === 'ArrowRight') dx = step;
    if (e.key === 'ArrowUp') dy = -step;
    if (e.key === 'ArrowDown') dy = step;
    moveSelectedObject(dx, dy);
    return;
  }
});

// ── Layers Sidebar List ───────────────────────────────────────────────────────
function renderSidebarList(pageIndex) {
  $layersSidebar.innerHTML = '<p class="layer-label">圖層列表</p>';
  const activeItems = getActivePageEdits(pageIndex);

  if (activeItems.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'text-sm text-hint';
    empty.textContent = '此頁沒有文字圖層';
    $layersSidebar.appendChild(empty);
    return;
  }

  activeItems.forEach((edit, idx) => {
    const card = document.createElement('div');
    card.className = 'layer-card-item' + (state.selectedObjId === edit.id ? ' active' : '');
    card.dataset.id = edit.id;

    const modeText = edit.mode === 'wordart' ? '文字藝術師' : '透明圖層';
    const isCustomNew = edit.id.startsWith('custom_text_');

    let thumbHtml = '';
    if (edit.mode === 'image_layer' && !isCustomNew) {
      const lIdx = (state.pages[pageIndex]?.layers || []).findIndex(l => l.id === edit.id);
      thumbHtml = `<img src="${getPageAssetUrl(pageIndex, 'layer_files', lIdx >= 0 ? lIdx : 0)}" alt="${edit.text}" loading="lazy">`;
    } else {
      thumbHtml = `<span style="font-size:.7rem; color:${edit.style?.color_hex || '#fff'}; font-weight:bold;">T</span>`;
    }

    const label = previewText(edit.text || `圖層 ${idx + 1}`, 34);

    card.innerHTML = `
      <div class="layer-card-thumb">${thumbHtml}</div>
      <div class="layer-card-info">
        <div class="layer-card-text">${escapeHtml(label)}</div>
        <div class="layer-card-mode-badge">${modeText}${isCustomNew ? ' (自訂)' : ''}</div>
      </div>
    `;

    card.addEventListener('click', () => {
      selectObject(edit.id);
    });

    $layersSidebar.appendChild(card);
  });
}

// ── State Management: Draft, Save, Discard ────────────────────────────────────
function markDirty() {
  state.isDirty = true;
  updateDraftControls();
}

function markClean() {
  state.isDirty = false;
  updateDraftControls();
}

function updateDraftControls() {
  $badgeDraft.classList.toggle('hidden', !state.isDirty);
  $btnSaveDraft.disabled = !state.isDirty;
  $btnDiscardDraft.disabled = !state.isDirty;
  updateUndoRedoButtons();
}

$btnSaveDraft.addEventListener('click', saveCustomEdits);
$btnDiscardDraft.addEventListener('click', discardCustomEdits);

async function saveCustomEdits() {
  if (!state.jobId || state.isBusy) return;
  setBusy(true, '正在儲存變更', '系統正在寫入本頁圖層與樣式設定。');
  try {
    const r = await fetch(`${API}/api/jobs/${state.jobId}/save_custom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.customEdits),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: '儲存失敗' }));
      throw new Error(err.detail);
    }
    markClean();
    toast('已儲存圖層與樣式設定', 'success');
  } catch (e) {
    toast(`儲存失敗：${e.message}`, 'error');
  } finally {
    setBusy(false);
  }
}

async function discardCustomEdits() {
  const ok = await confirmAction({
    title: '放棄本頁變更？',
    message: '這會還原目前頁面的文字圖層與樣式設定，尚未儲存的調整不會保留。',
    confirmLabel: '放棄變更',
    danger: true,
  });
  if (!ok) return;
  pushUndo();
  const pStr = String(state.selectedPageIndex);
  delete state.customEdits[pStr];
  initPageEdits(state.selectedPageIndex);
  selectPage(state.selectedPageIndex);
  markClean();
  toast('已還原為原始狀態', '');
}

// ── Action bar & Rebuild PPTX ─────────────────────────────────────────────────
function updateActionBar() {
  const sizeTxt = state.pages.length > 0 && state.jobSize
    ? ` · 暫存 <strong>${state.jobSize} MB</strong>`
    : '';
  $actionInfo.innerHTML = `
    <strong>${state.file?.name || ''}</strong>
    共 <strong>${state.pages.length}</strong> 頁，處理完成${sizeTxt}
  `;
}

$btnDownload.addEventListener('click', async () => {
  if (!state.jobId || state.isBusy) return;

  if (state.isDirty) {
    await saveCustomEdits();
    if (state.isDirty) return;
  }

  await triggerRebuild();
});

async function triggerRebuild() {
  if (!state.jobId || state.isBusy) return;

  toast('正在依照您的設定重組 PPTX 簡報…', '');
  setBusy(true, '正在重組 PPTX', '系統會依照目前圖層設定產生可下載簡報。');
  try {
    const r = await fetch(`${API}/api/jobs/${state.jobId}/rebuild`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: '重建失敗' }));
      throw new Error(err.detail);
    }
    await _waitForRebuild();
  } catch (e) {
    toast(e.message, 'error');
    setBusy(false);
  }
}

async function _waitForRebuild(maxWait = 60000) {
  const start = Date.now();
  while (Date.now() - start < maxWait) {
    await new Promise(r => setTimeout(r, 1500));
    const r = await fetch(`${API}/api/jobs/${state.jobId}/status`);
    const data = await r.json();
    if (data.rebuild_status === 'done') {
      const a = document.createElement('a');
      a.href = `${API}/api/jobs/${state.jobId}/download?custom=1`;
      a.download = '';
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast('PPTX 簡報下載完成！', 'success');
      setBusy(false);
      return;
    }
    if (data.rebuild_status === 'error') {
      toast('重建失敗：' + (data.rebuild_error || ''), 'error');
      setBusy(false);
      return;
    }
  }
  toast('重建超時，請再試一次', 'error');
  setBusy(false);
}

$btnDeleteJob.addEventListener('click', async () => {
  if (!state.jobId || state.isBusy) return;
  const ok = await confirmAction({
    title: '清除此工作？',
    message: '會刪除本次處理的暫存資料與結果檔。若還需要檔案，請先匯出 PPTX。',
    confirmLabel: '清除工作',
    danger: true,
  });
  if (!ok) return;
  setBusy(true, '正在清除工作', '正在移除暫存資料。');
  try {
    const r = await fetch(`${API}/api/jobs/${state.jobId}`, { method: 'DELETE' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: '清除失敗' }));
      throw new Error(err.detail);
    }
    toast('已清除工作暫存資料', 'success');
    clearFile();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    setBusy(false);
  }
});

// ── Params toggle ─────────────────────────────────────────────────────────────
$paramsToggle.addEventListener('click', toggleParams);
$paramsToggle.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    toggleParams();
  }
});

function toggleParams() {
  const open = $paramsBody.classList.toggle('open');
  $paramsToggle.classList.toggle('open', open);
  $paramsToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}

// ── Color Utilities ───────────────────────────────────────────────────────────
function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(x => {
    const hex = parseInt(x || 0).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('');
}

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? [
    parseInt(result[1], 16),
    parseInt(result[2], 16),
    parseInt(result[3], 16),
  ] : [255, 255, 255];
}

function escapeHtml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function loadCapabilities() {
  try {
    const response = await fetch(`${API}/api/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.uploadMode = data.upload_mode === 'gcs' ? 'gcs' : 'local';
    state.capabilitiesReady = true;
    document.body.dataset.uploadMode = state.uploadMode;
    $headerStatusText.textContent = state.uploadMode === 'gcs' ? '安全直傳模式' : '本機工作台';
    syncDisabledControls();
  } catch (error) {
    state.capabilitiesReady = false;
    console.error('capability check failed', error);
    $headerStatusText.textContent = '無法連線';
    toast('無法確認上傳模式，請重新整理頁面', 'error');
    syncDisabledControls();
  }
}

document.body.setAttribute('aria-busy', 'false');
loadCapabilities();
syncDisabledControls();
