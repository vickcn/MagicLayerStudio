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
  isCancelling: false,
  pollFailures: 0,
  pollAttempt: 0,
  pages: [],
  selectedPageIndex: 0,
  selectedView: 'editor',  // editor | source | background | layer
  selectedLayerIndex: 0,
  selectedObjIds: [],
  selectedObjId: null,
  activeInteraction: null,
  jobSize: null,
  
  // 自訂編輯資料：[pageIndex][objId] = { id, mode, text, x, y, width, height, rotation, lock_aspect, deleted, style: {...} }
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
const $btnCancelProcess = $('btn-cancel-process');
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
const $canvasGuides    = $('canvas-guides');
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
const $inspectorMulti   = $('inspector-multi');
const $multiCountLabel  = $('multi-count-label');
const $btnMultiCopy     = $('btn-multi-copy');
const $btnMultiDelete   = $('btn-multi-delete');
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
const $propValignTop    = $('prop-valign-top');
const $propValignMiddle = $('prop-valign-middle');
const $propValignBottom = $('prop-valign-bottom');

// WordArt Fill & Effects DOM
const $fillSolidBtn     = $('fill-solid-btn');
const $fillGradientBtn  = $('fill-gradient-btn');
const $fillSolidWrap    = $('fill-solid-wrap');
const $fillGradientWrap = $('fill-gradient-wrap');
const $propColor        = $('prop-color');
const $propColorHex     = $('prop-color-hex');
const $propGradC1       = $('prop-grad-c1');
const $propGradC1Hex    = $('prop-grad-c1-hex');
const $propGradC2       = $('prop-grad-c2');
const $propGradC2Hex    = $('prop-grad-c2-hex');
const $propGradAngle    = $('prop-grad-angle');
const $gradAngleLabel   = $('grad-angle-label');

const $propOutlineEnable = $('prop-outline-enable');
const $outlineBody      = $('outline-body');
const $propOutlineColor = $('prop-outline-color');
const $propOutlineColorHex = $('prop-outline-color-hex');
const $propOutlineWidth = $('prop-outline-width');

const $propShadowEnable = $('prop-shadow-enable');
const $shadowBody       = $('shadow-body');
const $propShadowColor  = $('prop-shadow-color');
const $propShadowColorHex = $('prop-shadow-color-hex');
const $propShadowOpacity = $('prop-shadow-opacity');
const $propShadowX      = $('prop-shadow-x');
const $propShadowY      = $('prop-shadow-y');
const $propShadowBlur   = $('prop-shadow-blur');

const $propPosX         = $('prop-pos-x');
const $propPosY         = $('prop-pos-y');
const $propPosW         = $('prop-pos-w');
const $propPosH         = $('prop-pos-h');
const $propLockAspect   = $('prop-lock-aspect');
const $propRotation     = $('prop-rotation');
const $propRotationSlider = $('prop-rotation-slider');
const $propRotationReset = $('prop-rotation-reset');
const $propOpacity      = $('prop-opacity');
const $opacityLabel     = $('opacity-label');
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
  const canCancel = state.uploadMode === 'gcs' && state.jobId && state.status === 'processing';
  $btnCancelProcess.classList.toggle('hidden', !canCancel);
  $btnCancelProcess.disabled = !canCancel || state.isCancelling;
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
$btnCancelProcess.addEventListener('click', cancelProcess);

async function cancelProcess() {
  if (!state.jobId || state.uploadMode !== 'gcs' || state.isCancelling) return;
  const ok = await confirmAction({
    title: '中止圖層分析？',
    message: '系統會通知 MagicLayerCore 停止此工作；目前正在執行的單一步驟會完成收尾後釋放資源。',
    confirmLabel: '中止處理',
    danger: true,
  });
  if (!ok) return;

  state.isCancelling = true;
  syncDisabledControls();
  $statusText.textContent = '正在通知 Core 中止處理…';
  try {
    const r = await fetch(`${API}/api/jobs/${encodeURIComponent(state.jobId)}/cancel`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: '中止失敗' }));
      throw new Error(err.detail || '中止失敗');
    }
    stopPolling();
    setStatus('error', '已通知 MagicLayerCore 中止處理。');
    toast('已通知 Core 中止處理', 'success');
  } catch (err) {
    toast(err.message || '中止失敗', 'error');
  } finally {
    state.isCancelling = false;
    syncDisabledControls();
  }
}

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
      if (!prepareRes.ok) throw new Error(await getApiErrorMessage(prepareRes, '無法準備安全上傳'));
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
      if (!completeRes.ok) throw new Error(await getApiErrorMessage(completeRes, 'Core 未能確認上傳檔案'));
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

async function getApiErrorMessage(response, fallback) {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
    return detail.message;
  }
  return typeof detail === 'string' && detail ? detail : fallback;
}

let _pollTimer = null;
let _pollInFlight = false;
const QUEUE_POLL_OFFLINE_THRESHOLD = 1;
const QUEUE_POLL_MAX_FAILURES = 2;

function stopPolling() {
  if (_pollTimer) clearTimeout(_pollTimer);
  _pollTimer = null;
  _pollInFlight = false;
}

const ACTIVE_POLL_BACKOFF_MS = [60_000, 120_000, 240_000, 480_000, 600_000];
const RECONNECT_POLL_MS = 15_000;

function pollStatus(job_id) {
  stopPolling();
  state.pollAttempt = 0;

  const runPoll = async () => {
    if (_pollInFlight) return;
    _pollInFlight = true;
    let shouldContinue = true;
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
      state.pollAttempt += 1;
      $statusText.textContent = data.progress || '處理中…';

      if (data.status === 'done') {
        shouldContinue = false;
        await loadResult(job_id);
      } else if (data.status === 'error') {
        shouldContinue = false;
        setStatus('error', data.progress || '處理失敗');
        toast(data.progress || '處理失敗', 'error');
      }
    } catch (err) {
      if (err.stopPolling) {
        shouldContinue = false;
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
        shouldContinue = false;
        const message = '服務暫時無法連線，已停止重試，請稍後再試。';
        setStatus('error', message);
        toast(message, 'error');
      }
    } finally {
      _pollInFlight = false;
      if (shouldContinue && state.jobId === job_id && !document.hidden) {
        const delay = state.pollFailures >= QUEUE_POLL_OFFLINE_THRESHOLD
          ? RECONNECT_POLL_MS
          : ACTIVE_POLL_BACKOFF_MS[Math.min(state.pollAttempt, ACTIVE_POLL_BACKOFF_MS.length - 1)];
        _pollTimer = setTimeout(runPoll, delay);
      }
    }
  };

  runPoll();
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden || !state.jobId || state.status !== 'processing') return;
  pollStatus(state.jobId);
});

async function loadResult(job_id) {
  state.jobId = job_id;
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
  state.pollAttempt = 0;
  state.isCancelling = false;
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

  if (state.uploadMode === 'gcs' && typeof value === 'string' && value) {
    const safePath = value.split('/').map(encodeURIComponent).join('/');
    return `${API}/api/jobs/${encodeURIComponent(state.jobId)}/artifacts/${safePath}`;
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

// ── Render Interactive Overlay & PPT Simulator Controls ──────────────────────
function renderInteractiveOverlay(pageIndex) {
  $canvasOverlay.innerHTML = '';
  clearSnapGuides();

  $canvasOverlay.onmousedown = (e) => {
    if (e.target === $canvasOverlay) {
      deselectObject();
    }
  };

  const activeItems = getActivePageEdits(pageIndex);
  const natW = state.canvasNaturalSize.width || 1920;
  const natH = state.canvasNaturalSize.height || 1080;

  activeItems.forEach((edit) => {
    const isSelected = state.selectedObjId === edit.id;
    const isMultiSelected = state.selectedObjIds.includes(edit.id) && !isSelected;

    const item = document.createElement('div');
    item.className = 'canvas-item' +
      (isSelected ? ' selected' : '') +
      (isMultiSelected ? ' multi-selected' : '');
    item.id = `canvas-item-${edit.id}`;
    item.dataset.id = edit.id;

    updateCanvasItemStyle(item, edit, natW, natH);
    renderItemContent(item, edit, pageIndex);

    // 建立 8 個縮放控制點與 1 個旋轉控制點
    const handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
    handles.forEach((dir) => {
      const h = document.createElement('div');
      h.className = `resize-handle handle-${dir}`;
      h.dataset.handle = dir;
      attachResizeHandle(h, dir, edit.id, pageIndex);
      item.appendChild(h);
    });

    const rotStem = document.createElement('div');
    rotStem.className = 'rotate-handle-stem';
    item.appendChild(rotStem);

    const rotHandle = document.createElement('div');
    rotHandle.className = 'rotate-handle';
    rotHandle.title = '旋轉物件（拖曳時按 Shift 可依 15° 增量吸附）';
    attachRotateHandle(rotHandle, edit.id, pageIndex);
    item.appendChild(rotHandle);

    attachDragAndSelect(item, edit.id, pageIndex);

    $canvasOverlay.appendChild(item);
  });
}

function updateCanvasItemStyle(el, edit, natW, natH) {
  const leftPct = (edit.x / natW) * 100;
  const topPct = (edit.y / natH) * 100;
  const widthPct = (edit.width / natW) * 100;
  const heightPct = (edit.height / natH) * 100;
  const rot = edit.rotation || 0;
  const opacity = edit.opacity !== undefined ? edit.opacity : 1;

  el.style.left = `${leftPct}%`;
  el.style.top = `${topPct}%`;
  el.style.width = `${widthPct}%`;
  el.style.height = `${heightPct}%`;
  el.style.transform = rot ? `rotate(${rot}deg)` : 'none';
  el.style.opacity = `${opacity}`;
}

function renderItemContent(itemEl, edit, pageIndex) {
  // 只清除內容，保留 handles
  const existingHandles = itemEl.querySelectorAll('.resize-handle, .rotate-handle, .rotate-handle-stem');
  itemEl.innerHTML = '';
  existingHandles.forEach(h => itemEl.appendChild(h));

  const isCustomNew = edit.id.startsWith('custom_text_');

  if (edit.mode === 'image_layer' && !isCustomNew) {
    const img = document.createElement('img');
    img.className = 'canvas-item-img';
    const lIdx = (state.pages[pageIndex]?.layers || []).findIndex(l => l.id === edit.id);
    img.src = getPageAssetUrl(pageIndex, 'layer_files', lIdx >= 0 ? lIdx : 0);
    img.alt = edit.text || '文字圖層';
    itemEl.insertBefore(img, itemEl.firstChild);
  } else {
    // wordart 模式
    const wordart = document.createElement('div');
    const s = edit.style || {};
    const vAlign = s.vertical_align || 'middle';
    wordart.className = `wordart-preview valign-${vAlign}`;
    wordart.textContent = edit.text;

    wordart.style.fontFamily = `"${s.font_name || 'Noto Sans TC'}", "Noto Sans TC", sans-serif`;
    wordart.style.fontWeight = s.bold ? '700' : '400';
    wordart.style.fontStyle = s.italic ? 'italic' : 'normal';
    wordart.style.textAlign = s.align || 'center';

    const stageH = $canvasStage.clientHeight || 480;
    const scaleRatio = stageH / (state.canvasNaturalSize.height || 1080);
    const scaledPx = Math.max(10, Math.round(((s.font_size_pt || 24) * 1.333) * scaleRatio));
    wordart.style.fontSize = `${scaledPx}px`;

    // 1. 填色處理 (單色 vs 漸層)
    const fill = s.fill || { type: 'solid', color: s.color_hex || '#FFFFFF' };
    if (fill.type === 'gradient' && Array.isArray(fill.colors) && fill.colors.length >= 2) {
      const angle = fill.angle !== undefined ? fill.angle : 90;
      wordart.style.backgroundImage = `linear-gradient(${angle}deg, ${fill.colors[0]}, ${fill.colors[1]})`;
      wordart.style.webkitBackgroundClip = 'text';
      wordart.style.webkitTextFillColor = 'transparent';
      wordart.style.color = 'transparent';
    } else {
      wordart.style.backgroundImage = 'none';
      wordart.style.webkitBackgroundClip = 'initial';
      wordart.style.webkitTextFillColor = 'initial';
      wordart.style.color = fill.color || s.color_hex || '#FFFFFF';
    }

    // 2. 文字外框 (Outline)
    const outline = s.outline || {};
    if (outline.enabled && outline.width > 0) {
      const strokeScaled = Math.max(1, Math.round((outline.width || 2) * scaleRatio * 1.2));
      wordart.style.webkitTextStroke = `${strokeScaled}px ${outline.color || '#7A2E00'}`;
      wordart.style.paintOrder = 'stroke fill';
    } else {
      wordart.style.webkitTextStroke = '0px transparent';
    }

    // 3. 文字陰影 (Shadow)
    const shadow = s.shadow || {};
    if (shadow.enabled) {
      const shColor = shadow.color || '#000000';
      const shOpacity = shadow.opacity !== undefined ? shadow.opacity : 0.35;
      const shRgb = hexToRgb(shColor) || [0, 0, 0];
      const shRgba = `rgba(${shRgb[0]}, ${shRgb[1]}, ${shRgb[2]}, ${shOpacity})`;
      const sx = Math.round((shadow.offset_x || 4) * scaleRatio);
      const sy = Math.round((shadow.offset_y || 4) * scaleRatio);
      const sblur = Math.round((shadow.blur || 8) * scaleRatio);
      wordart.style.textShadow = `${sx}px ${sy}px ${sblur}px ${shRgba}`;
    } else {
      wordart.style.textShadow = 'none';
    }

    itemEl.insertBefore(wordart, itemEl.firstChild);
  }
}

// ── Smart Snap Guides ─────────────────────────────────────────────────────────
function clearSnapGuides() {
  if ($canvasGuides) $canvasGuides.innerHTML = '';
}

function drawSnapGuides(guidesX, guidesY, natW, natH) {
  if (!$canvasGuides) return;
  $canvasGuides.innerHTML = '';

  guidesX.forEach((gx) => {
    const line = document.createElement('div');
    line.className = 'snap-guide-x';
    line.style.left = `${(gx / natW) * 100}%`;
    $canvasGuides.appendChild(line);
  });

  guidesY.forEach((gy) => {
    const line = document.createElement('div');
    line.className = 'snap-guide-y';
    line.style.top = `${(gy / natH) * 100}%`;
    $canvasGuides.appendChild(line);
  });
}

function computeSnap(activeEdits, currentEditId, targetBox, natW, natH, stageRect) {
  const thresholdPx = 6;
  const scaleX = natW / stageRect.width;
  const scaleY = natH / stageRect.height;
  const thresholdX = thresholdPx * scaleX;
  const thresholdY = thresholdPx * scaleY;

  let snappedX = targetBox.x;
  let snappedY = targetBox.y;
  const guidesX = [];
  const guidesY = [];

  const candidateX = [
    { pos: 0, desc: 'left-boundary' },
    { pos: Math.round(natW / 2), desc: 'center-x' },
    { pos: natW, desc: 'right-boundary' }
  ];

  const candidateY = [
    { pos: 0, desc: 'top-boundary' },
    { pos: Math.round(natH / 2), desc: 'center-y' },
    { pos: natH, desc: 'bottom-boundary' }
  ];

  activeEdits.forEach((item) => {
    if (item.id === currentEditId || item.deleted) return;
    candidateX.push({ pos: item.x, desc: 'other-left' });
    candidateX.push({ pos: Math.round(item.x + item.width / 2), desc: 'other-center-x' });
    candidateX.push({ pos: item.x + item.width, desc: 'other-right' });

    candidateY.push({ pos: item.y, desc: 'other-top' });
    candidateY.push({ pos: Math.round(item.y + item.height / 2), desc: 'other-center-y' });
    candidateY.push({ pos: item.y + item.height, desc: 'other-bottom' });
  });

  const curLeft = targetBox.x;
  const curCenterX = Math.round(targetBox.x + targetBox.width / 2);
  const curRight = targetBox.x + targetBox.width;

  let minDiffX = thresholdX;
  candidateX.forEach((c) => {
    // 檢查靠左
    if (Math.abs(curLeft - c.pos) < minDiffX) {
      minDiffX = Math.abs(curLeft - c.pos);
      snappedX = c.pos;
      guidesX.length = 0;
      guidesX.push(c.pos);
    }
    // 檢查置中
    if (Math.abs(curCenterX - c.pos) < minDiffX) {
      minDiffX = Math.abs(curCenterX - c.pos);
      snappedX = c.pos - Math.round(targetBox.width / 2);
      guidesX.length = 0;
      guidesX.push(c.pos);
    }
    // 檢查靠右
    if (Math.abs(curRight - c.pos) < minDiffX) {
      minDiffX = Math.abs(curRight - c.pos);
      snappedX = c.pos - targetBox.width;
      guidesX.length = 0;
      guidesX.push(c.pos);
    }
  });

  const curTop = targetBox.y;
  const curCenterY = Math.round(targetBox.y + targetBox.height / 2);
  const curBottom = targetBox.y + targetBox.height;

  let minDiffY = thresholdY;
  candidateY.forEach((c) => {
    // 檢查靠頂
    if (Math.abs(curTop - c.pos) < minDiffY) {
      minDiffY = Math.abs(curTop - c.pos);
      snappedY = c.pos;
      guidesY.length = 0;
      guidesY.push(c.pos);
    }
    // 檢查垂直置中
    if (Math.abs(curCenterY - c.pos) < minDiffY) {
      minDiffY = Math.abs(curCenterY - c.pos);
      snappedY = c.pos - Math.round(targetBox.height / 2);
      guidesY.length = 0;
      guidesY.push(c.pos);
    }
    // 檢查靠底
    if (Math.abs(curBottom - c.pos) < minDiffY) {
      minDiffY = Math.abs(curBottom - c.pos);
      snappedY = c.pos - targetBox.height;
      guidesY.length = 0;
      guidesY.push(c.pos);
    }
  });

  return { snappedX, snappedY, guidesX, guidesY };
}

// ── Drag & Select Handler (支援多選群組移動、對齊吸附與行動觸控) ─────────────
function attachDragAndSelect(el, objId, pageIndex) {
  el.addEventListener('pointerdown', (e) => {
    if (e.target.classList.contains('resize-handle') || e.target.classList.contains('rotate-handle')) {
      return;
    }
    e.stopPropagation();

    const isMultiKey = e.ctrlKey || e.metaKey || e.shiftKey;
    if (isMultiKey) {
      toggleObjectSelection(objId);
      return;
    }

    if (!state.selectedObjIds.includes(objId)) {
      selectObject(objId);
    }

    const stageRect = $canvasStage.getBoundingClientRect();
    const natW = state.canvasNaturalSize.width || 1920;
    const natH = state.canvasNaturalSize.height || 1080;
    const activeEdits = getActivePageEdits(pageIndex);

    const startMouseX = e.clientX;
    const startMouseY = e.clientY;

    const initialPositions = new Map();
    state.selectedObjIds.forEach((id) => {
      const ed = getObjectEdit(pageIndex, id);
      if (ed) {
        initialPositions.set(id, { x: ed.x, y: ed.y, width: ed.width, height: ed.height, rotation: ed.rotation || 0 });
      }
    });

    const primaryInitial = initialPositions.get(objId);
    if (!primaryInitial) return;

    let hasMoved = false;

    state.activeInteraction = {
      type: 'drag',
      pageIndex,
      initialPositions,
      cancel: () => {
        initialPositions.forEach((pos, id) => {
          const ed = getObjectEdit(pageIndex, id);
          if (ed) {
            ed.x = pos.x;
            ed.y = pos.y;
            const dom = document.getElementById(`canvas-item-${id}`);
            if (dom) updateCanvasItemStyle(dom, ed, natW, natH);
          }
        });
        clearSnapGuides();
        const curEd = getObjectEdit(pageIndex, state.selectedObjId);
        if (curEd) updateInspectorPosition(curEd);
      }
    };

    function onPointerMove(moveEvent) {
      const dxPx = moveEvent.clientX - startMouseX;
      const dyPx = moveEvent.clientY - startMouseY;

      if (!hasMoved && (Math.abs(dxPx) > 2 || Math.abs(dyPx) > 2)) {
        hasMoved = true;
        pushUndo();
      }

      const scaleX = natW / stageRect.width;
      const scaleY = natH / stageRect.height;
      const rawNewX = primaryInitial.x + dxPx * scaleX;
      const rawNewY = primaryInitial.y + dyPx * scaleY;

      const snapRes = computeSnap(
        activeEdits,
        objId,
        { x: rawNewX, y: rawNewY, width: primaryInitial.width, height: primaryInitial.height },
        natW,
        natH,
        stageRect
      );

      const effectiveDx = snapRes.snappedX - primaryInitial.x;
      const effectiveDy = snapRes.snappedY - primaryInitial.y;

      drawSnapGuides(snapRes.guidesX, snapRes.guidesY, natW, natH);

      state.selectedObjIds.forEach((id) => {
        const ed = getObjectEdit(pageIndex, id);
        const init = initialPositions.get(id);
        if (ed && init) {
          const nx = Math.round(init.x + effectiveDx);
          const ny = Math.round(init.y + effectiveDy);
          ed.x = Math.max(0, Math.min(natW - ed.width, nx));
          ed.y = Math.max(0, Math.min(natH - ed.height, ny));

          const dom = document.getElementById(`canvas-item-${id}`);
          if (dom) updateCanvasItemStyle(dom, ed, natW, natH);
        }
      });

      const primaryEdit = getObjectEdit(pageIndex, state.selectedObjId);
      if (primaryEdit) updateInspectorPosition(primaryEdit);
      markDirty();
    }

    function onPointerUp() {
      state.activeInteraction = null;
      clearSnapGuides();
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
    }

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
  });
}

// ── 8 Resize Handles Handler (支援行動觸控 / Shift 比例 / Alt 中心縮放) ──────
function attachResizeHandle(handleEl, dir, objId, pageIndex) {
  handleEl.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    selectObject(objId);

    const edit = getObjectEdit(pageIndex, objId);
    if (!edit) return;

    const stageRect = $canvasStage.getBoundingClientRect();
    const natW = state.canvasNaturalSize.width || 1920;
    const natH = state.canvasNaturalSize.height || 1080;

    const startMouseX = e.clientX;
    const startMouseY = e.clientY;
    const startX = edit.x;
    const startY = edit.y;
    const startW = edit.width;
    const startH = edit.height;
    const initialAspect = startW / (startH || 1);

    let hasMoved = false;

    state.activeInteraction = {
      type: 'resize',
      pageIndex,
      cancel: () => {
        edit.x = startX;
        edit.y = startY;
        edit.width = startW;
        edit.height = startH;
        const dom = document.getElementById(`canvas-item-${objId}`);
        if (dom) {
          updateCanvasItemStyle(dom, edit, natW, natH);
          renderItemContent(dom, edit, pageIndex);
        }
        clearSnapGuides();
        updateInspectorPosition(edit);
      }
    };

    function onPointerMove(moveEvent) {
      const dxPx = moveEvent.clientX - startMouseX;
      const dyPx = moveEvent.clientY - startMouseY;

      if (!hasMoved && (Math.abs(dxPx) > 2 || Math.abs(dyPx) > 2)) {
        hasMoved = true;
        pushUndo();
      }

      const scaleX = natW / stageRect.width;
      const scaleY = natH / stageRect.height;
      const dx = dxPx * scaleX;
      const dy = dyPx * scaleY;

      let newX = startX;
      let newY = startY;
      let newW = startW;
      let newH = startH;

      const shouldLockAspect = moveEvent.shiftKey || edit.lock_aspect || edit.mode === 'image_layer';
      const fromCenter = moveEvent.altKey;

      if (dir.includes('e')) newW = startW + (fromCenter ? dx * 2 : dx);
      if (dir.includes('w')) {
        newW = startW - (fromCenter ? dx * 2 : dx);
        if (!fromCenter) newX = startX + dx;
      }
      if (dir.includes('s')) newH = startH + (fromCenter ? dy * 2 : dy);
      if (dir.includes('n')) {
        newH = startH - (fromCenter ? dy * 2 : dy);
        if (!fromCenter) newY = startY + dy;
      }

      // 鎖定長寬比
      if (shouldLockAspect && (dir === 'nw' || dir === 'ne' || dir === 'se' || dir === 'sw')) {
        const aspectW = newH * initialAspect;
        const aspectH = newW / initialAspect;
        if (Math.abs(dx) > Math.abs(dy)) {
          newH = aspectH;
          if (dir.includes('n') && !fromCenter) newY = startY + (startH - newH);
        } else {
          newW = aspectW;
          if (dir.includes('w') && !fromCenter) newX = startX + (startW - newW);
        }
      }

      if (fromCenter) {
        newX = startX - (newW - startW) / 2;
        newY = startY - (newH - startH) / 2;
      }

      // 限制最小尺寸與邊界
      newW = Math.max(20, Math.round(newW));
      newH = Math.max(16, Math.round(newH));
      newX = Math.max(0, Math.min(natW - newW, Math.round(newX)));
      newY = Math.max(0, Math.min(natH - newH, Math.round(newY)));

      edit.x = newX;
      edit.y = newY;
      edit.width = newW;
      edit.height = newH;

      const dom = document.getElementById(`canvas-item-${objId}`);
      if (dom) {
        updateCanvasItemStyle(dom, edit, natW, natH);
        renderItemContent(dom, edit, pageIndex);
      }
      updateInspectorPosition(edit);
      markDirty();
    }

    function onPointerUp() {
      state.activeInteraction = null;
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
    }

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
  });
}

// ── Rotate Handle Handler (支援行動觸控 / Shift 15° 吸附) ────────────────────
function attachRotateHandle(handleEl, objId, pageIndex) {
  handleEl.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    selectObject(objId);

    const edit = getObjectEdit(pageIndex, objId);
    if (!edit) return;

    const dom = document.getElementById(`canvas-item-${objId}`);
    if (!dom) return;

    const rect = dom.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const startRot = edit.rotation || 0;

    let hasMoved = false;

    state.activeInteraction = {
      type: 'rotate',
      pageIndex,
      cancel: () => {
        edit.rotation = startRot;
        if (dom) updateCanvasItemStyle(dom, edit, state.canvasNaturalSize.width, state.canvasNaturalSize.height);
        if ($propRotation) $propRotation.value = startRot;
        if ($propRotationSlider) $propRotationSlider.value = startRot;
      }
    };

    function onPointerMove(moveEvent) {
      if (!hasMoved) {
        hasMoved = true;
        pushUndo();
      }

      const mouseX = moveEvent.clientX;
      const mouseY = moveEvent.clientY;
      const rad = Math.atan2(mouseY - centerY, mouseX - centerX);
      let deg = Math.round((rad * 180) / Math.PI) + 90;

      // 正規化至 -180 ~ 180
      if (deg > 180) deg -= 360;
      if (deg < -180) deg += 360;

      // Shift: 15 度增量吸附
      if (moveEvent.shiftKey) {
        deg = Math.round(deg / 15) * 15;
      }

      edit.rotation = deg;
      updateCanvasItemStyle(dom, edit, state.canvasNaturalSize.width, state.canvasNaturalSize.height);

      if ($propRotation) $propRotation.value = deg;
      if ($propRotationSlider) $propRotationSlider.value = deg;
      markDirty();
    }

    function onPointerUp() {
      state.activeInteraction = null;
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
    }

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
  });
}

// ── Selection State Management ────────────────────────────────────────────────
function selectObject(objId) {
  state.selectedObjIds = [objId];
  state.selectedObjId = objId;
  syncSelectionClasses();
  openInspector(objId);
}

function toggleObjectSelection(objId) {
  const idx = state.selectedObjIds.indexOf(objId);
  if (idx >= 0) {
    state.selectedObjIds.splice(idx, 1);
    state.selectedObjId = state.selectedObjIds[state.selectedObjIds.length - 1] || null;
  } else {
    state.selectedObjIds.push(objId);
    state.selectedObjId = objId;
  }
  syncSelectionClasses();

  if (state.selectedObjIds.length === 0) {
    closeInspector();
  } else if (state.selectedObjIds.length === 1) {
    openInspector(state.selectedObjId);
  } else {
    openMultiInspector();
  }
}

function deselectObject() {
  state.selectedObjIds = [];
  state.selectedObjId = null;
  syncSelectionClasses();
  clearSnapGuides();
  closeInspector();
}

function syncSelectionClasses() {
  document.querySelectorAll('.canvas-item').forEach((item) => {
    const id = item.dataset.id;
    const isPrimary = state.selectedObjId === id;
    const isMulti = state.selectedObjIds.includes(id) && !isPrimary;
    item.classList.toggle('selected', isPrimary);
    item.classList.toggle('multi-selected', isMulti);
  });

  document.querySelectorAll('.layer-card-item').forEach((card) => {
    const id = card.dataset.id;
    card.classList.toggle('active', state.selectedObjIds.includes(id));
  });
}

// ── Inspector Panel Logic ─────────────────────────────────────────────────────
function openInspector(objId) {
  const edit = getObjectEdit(state.selectedPageIndex, objId);
  if (!edit) { closeInspector(); return; }

  $inspectorEmpty.classList.add('hidden');
  $inspectorMulti.classList.add('hidden');
  $inspectorBody.classList.remove('hidden');
  $inspectorObjId.textContent = objId.startsWith('custom_text_') ? '自訂文字方塊' : objId;

  // 模式按鈕狀態
  $modeImageBtn.classList.toggle('active', edit.mode === 'image_layer');
  $modeWordartBtn.classList.toggle('active', edit.mode === 'wordart');

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

  const vAlign = s.vertical_align || 'middle';
  $propValignTop.classList.toggle('active', vAlign === 'top');
  $propValignMiddle.classList.toggle('active', vAlign === 'middle');
  $propValignBottom.classList.toggle('active', vAlign === 'bottom');

  // 填色 (單色 vs 漸層)
  const fill = s.fill || { type: 'solid', color: s.color_hex || '#ffffff' };
  const isGradient = fill.type === 'gradient';
  $fillSolidBtn.classList.toggle('active', !isGradient);
  $fillGradientBtn.classList.toggle('active', isGradient);
  $fillSolidWrap.classList.toggle('hidden', isGradient);
  $fillGradientWrap.classList.toggle('hidden', !isGradient);

  $propColor.value = fill.color || s.color_hex || '#ffffff';
  $propColorHex.value = (fill.color || s.color_hex || '#FFFFFF').toUpperCase();

  const colors = fill.colors || ['#FFE082', '#F57C00'];
  $propGradC1.value = colors[0] || '#FFE082';
  $propGradC1Hex.value = (colors[0] || '#FFE082').toUpperCase();
  $propGradC2.value = colors[1] || '#F57C00';
  $propGradC2Hex.value = (colors[1] || '#F57C00').toUpperCase();
  const gradAng = fill.angle !== undefined ? fill.angle : 90;
  $propGradAngle.value = gradAng;
  $gradAngleLabel.textContent = `${gradAng}°`;

  // 外框 (Outline)
  const outline = s.outline || { enabled: false, color: '#7A2E00', width: 2 };
  $propOutlineEnable.checked = Boolean(outline.enabled);
  $outlineBody.classList.toggle('hidden', !outline.enabled);
  $propOutlineColor.value = outline.color || '#7A2E00';
  $propOutlineColorHex.value = (outline.color || '#7A2E00').toUpperCase();
  $propOutlineWidth.value = outline.width !== undefined ? outline.width : 2;

  // 陰影 (Shadow)
  const shadow = s.shadow || { enabled: false, color: '#000000', opacity: 0.35, offset_x: 4, offset_y: 4, blur: 8 };
  $propShadowEnable.checked = Boolean(shadow.enabled);
  $shadowBody.classList.toggle('hidden', !shadow.enabled);
  $propShadowColor.value = shadow.color || '#000000';
  $propShadowColorHex.value = (shadow.color || '#000000').toUpperCase();
  $propShadowOpacity.value = shadow.opacity !== undefined ? shadow.opacity : 0.35;
  $propShadowX.value = shadow.offset_x !== undefined ? shadow.offset_x : 4;
  $propShadowY.value = shadow.offset_y !== undefined ? shadow.offset_y : 4;
  $propShadowBlur.value = shadow.blur !== undefined ? shadow.blur : 8;

  // 比例鎖定、旋轉與不透明度
  const isLocked = edit.lock_aspect !== undefined ? Boolean(edit.lock_aspect) : (edit.mode === 'image_layer');
  $propLockAspect.classList.toggle('active', isLocked);
  $propLockAspect.title = isLocked ? '寬高比例已鎖定' : '寬高比例未鎖定';

  const rot = edit.rotation || 0;
  $propRotation.value = rot;
  $propRotationSlider.value = rot;

  const op = edit.opacity !== undefined ? edit.opacity : 1;
  $propOpacity.value = op;
  $opacityLabel.textContent = `${Math.round(op * 100)}%`;

  // 座標
  updateInspectorPosition(edit);
}

function openMultiInspector() {
  $inspectorEmpty.classList.add('hidden');
  $inspectorBody.classList.add('hidden');
  $inspectorMulti.classList.remove('hidden');
  $inspectorObjId.textContent = `${state.selectedObjIds.length} 個物件`;
  $multiCountLabel.textContent = `已選取 ${state.selectedObjIds.length} 個物件`;
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
  $inspectorMulti.classList.add('hidden');
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

$propValignTop.addEventListener('click', () => { pushUndo(); setVerticalAlign('top'); });
$propValignMiddle.addEventListener('click', () => { pushUndo(); setVerticalAlign('middle'); });
$propValignBottom.addEventListener('click', () => { pushUndo(); setVerticalAlign('bottom'); });

function setVerticalAlign(valign) {
  $propValignTop.classList.toggle('active', valign === 'top');
  $propValignMiddle.classList.toggle('active', valign === 'middle');
  $propValignBottom.classList.toggle('active', valign === 'bottom');
  updateCurrentStyle({ vertical_align: valign });
}

// ── Fill (Solid vs Gradient) Bindings ────────────────────────────────────────
$fillSolidBtn.addEventListener('click', () => setFillMode('solid'));
$fillGradientBtn.addEventListener('click', () => setFillMode('gradient'));

function setFillMode(fillType) {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  pushUndo();
  const s = edit.style || {};
  const currentFill = s.fill || { type: 'solid', color: s.color_hex || '#FFFFFF' };
  currentFill.type = fillType;

  if (fillType === 'gradient' && (!currentFill.colors || currentFill.colors.length < 2)) {
    currentFill.colors = [$propGradC1.value, $propGradC2.value];
    currentFill.angle = parseInt($propGradAngle.value) || 90;
  }

  $fillSolidBtn.classList.toggle('active', fillType === 'solid');
  $fillGradientBtn.classList.toggle('active', fillType === 'gradient');
  $fillSolidWrap.classList.toggle('hidden', fillType === 'gradient');
  $fillGradientWrap.classList.toggle('hidden', fillType === 'solid');

  updateCurrentStyle({ fill: currentFill });
}

$propGradAngle.addEventListener('input', (e) => {
  const angle = parseInt(e.target.value) || 0;
  $gradAngleLabel.textContent = `${angle}°`;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;
  const fill = edit.style?.fill || { type: 'gradient', colors: [$propGradC1.value, $propGradC2.value], angle: 90 };
  fill.angle = angle;
  updateCurrentStyle({ fill });
});

[$propGradC1, $propGradC2].forEach((inp, idx) => {
  inp.addEventListener('input', (e) => {
    const hex = e.target.value.toUpperCase();
    if (idx === 0) $propGradC1Hex.value = hex;
    else $propGradC2Hex.value = hex;
    updateGradientColors();
  });
});

[$propGradC1Hex, $propGradC2Hex].forEach((inp, idx) => {
  inp.addEventListener('change', (e) => {
    let hex = e.target.value.trim();
    if (!hex.startsWith('#')) hex = '#' + hex;
    if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
      pushUndo();
      if (idx === 0) $propGradC1.value = hex;
      else $propGradC2.value = hex;
      updateGradientColors();
    }
  });
});

function updateGradientColors() {
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;
  const fill = edit.style?.fill || { type: 'gradient', angle: 90 };
  fill.colors = [$propGradC1.value, $propGradC2.value];
  updateCurrentStyle({ fill });
}

// ── Outline & Shadow Bindings ────────────────────────────────────────────────
$propOutlineEnable.addEventListener('change', (e) => {
  pushUndo();
  const enabled = e.target.checked;
  $outlineBody.classList.toggle('hidden', !enabled);
  updateCurrentStyle({
    outline: {
      enabled,
      color: $propOutlineColor.value,
      width: parseInt($propOutlineWidth.value) || 2,
    }
  });
});

$propOutlineColor.addEventListener('input', (e) => {
  $propOutlineColorHex.value = e.target.value.toUpperCase();
  updateOutlineStyle();
});

$propOutlineColorHex.addEventListener('change', (e) => {
  let hex = e.target.value.trim();
  if (!hex.startsWith('#')) hex = '#' + hex;
  if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
    pushUndo();
    $propOutlineColor.value = hex;
    updateOutlineStyle();
  }
});

$propOutlineWidth.addEventListener('input', updateOutlineStyle);

function updateOutlineStyle() {
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;
  updateCurrentStyle({
    outline: {
      enabled: $propOutlineEnable.checked,
      color: $propOutlineColor.value,
      width: parseInt($propOutlineWidth.value) || 2,
    }
  });
}

$propShadowEnable.addEventListener('change', (e) => {
  pushUndo();
  const enabled = e.target.checked;
  $shadowBody.classList.toggle('hidden', !enabled);
  updateShadowStyle();
});

$propShadowColor.addEventListener('input', (e) => {
  $propShadowColorHex.value = e.target.value.toUpperCase();
  updateShadowStyle();
});

$propShadowColorHex.addEventListener('change', (e) => {
  let hex = e.target.value.trim();
  if (!hex.startsWith('#')) hex = '#' + hex;
  if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
    pushUndo();
    $propShadowColor.value = hex;
    updateShadowStyle();
  }
});

[$propShadowOpacity, $propShadowX, $propShadowY, $propShadowBlur].forEach((inp) => {
  inp.addEventListener('input', updateShadowStyle);
});

function updateShadowStyle() {
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;
  updateCurrentStyle({
    shadow: {
      enabled: $propShadowEnable.checked,
      color: $propShadowColor.value,
      opacity: parseFloat($propShadowOpacity.value) || 0.35,
      offset_x: parseInt($propShadowX.value) || 4,
      offset_y: parseInt($propShadowY.value) || 4,
      blur: parseInt($propShadowBlur.value) || 8,
    }
  });
}

// ── Opacity Binding ──────────────────────────────────────────────────────────
$propOpacity.addEventListener('input', (e) => {
  const op = parseFloat(e.target.value) || 1;
  $opacityLabel.textContent = `${Math.round(op * 100)}%`;
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;
  edit.opacity = op;
  const el = document.getElementById(`canvas-item-${edit.id}`);
  if (el) el.style.opacity = `${op}`;
  markDirty();
});

$propLockAspect.addEventListener('click', () => {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  pushUndo();
  const current = edit.lock_aspect !== undefined ? Boolean(edit.lock_aspect) : (edit.mode === 'image_layer');
  edit.lock_aspect = !current;
  $propLockAspect.classList.toggle('active', edit.lock_aspect);
  $propLockAspect.title = edit.lock_aspect ? '寬高比例已鎖定' : '寬高比例未鎖定';
  toast(edit.lock_aspect ? '已鎖定比例' : '已解除比例鎖定', '');
  markDirty();
});

$propRotationSlider.addEventListener('input', (e) => {
  const val = parseInt(e.target.value) || 0;
  $propRotation.value = val;
  setRotation(val, false);
});

$propRotation.addEventListener('change', (e) => {
  let val = parseInt(e.target.value) || 0;
  if (val > 180) val = 180;
  if (val < -180) val = -180;
  $propRotation.value = val;
  $propRotationSlider.value = val;
  pushUndo();
  setRotation(val, true);
});

$propRotationReset.addEventListener('click', () => {
  pushUndo();
  $propRotation.value = 0;
  $propRotationSlider.value = 0;
  setRotation(0, true);
});

function setRotation(deg, commitHistory = false) {
  if (!state.selectedObjId) return;
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  if (!edit) return;

  if (commitHistory) pushUndo();
  edit.rotation = deg;
  const el = document.getElementById(`canvas-item-${edit.id}`);
  if (el) {
    updateCanvasItemStyle(el, edit, state.canvasNaturalSize.width, state.canvasNaturalSize.height);
  }
  markDirty();
}

$propColor.addEventListener('input', (e) => {
  const hex = e.target.value.toUpperCase();
  $propColorHex.value = hex;
  const rgb = hexToRgb(hex);
  const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
  const fill = edit?.style?.fill || { type: 'solid', color: hex };
  fill.color = hex;
  updateCurrentStyle({ color_hex: hex, color_rgb: rgb, fill });
});

$propColorHex.addEventListener('change', (e) => {
  let hex = e.target.value.trim();
  if (!hex.startsWith('#')) hex = '#' + hex;
  if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
    pushUndo();
    $propColor.value = hex;
    const rgb = hexToRgb(hex);
    const edit = getObjectEdit(state.selectedPageIndex, state.selectedObjId);
    const fill = edit?.style?.fill || { type: 'solid', color: hex.toUpperCase() };
    fill.color = hex.toUpperCase();
    updateCurrentStyle({ color_hex: hex.toUpperCase(), color_rgb: rgb, fill });
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
      renderItemContent(el, edit, state.selectedPageIndex);
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

// ── Object Actions: Add / Copy / Paste / Delete (支援多選群組) ───────────────
$btnAddText.addEventListener('click', addNewTextObject);
$btnCopyObj.addEventListener('click', copySelectedObjects);
$btnDeleteObj.addEventListener('click', deleteSelectedObjects);
$btnMultiCopy.addEventListener('click', copySelectedObjects);
$btnMultiDelete.addEventListener('click', deleteSelectedObjects);

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
    rotation: 0,
    lock_aspect: false,
    deleted: false,
    style: {
      font_name: 'Noto Sans TC',
      font_size_pt: 32,
      bold: true,
      italic: false,
      align: 'center',
      vertical_align: 'middle',
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

function copySelectedObjects() {
  const ids = state.selectedObjIds.length > 0 ? state.selectedObjIds : (state.selectedObjId ? [state.selectedObjId] : []);
  if (ids.length === 0) return;

  const itemsToCopy = [];
  ids.forEach((id) => {
    const edit = getObjectEdit(state.selectedPageIndex, id);
    if (edit) itemsToCopy.push(JSON.parse(JSON.stringify(edit)));
  });

  if (itemsToCopy.length === 0) return;

  state.clipboard = itemsToCopy;

  ids.forEach((id) => {
    const el = document.getElementById(`canvas-item-${id}`);
    if (el) {
      el.classList.remove('pulse-copy');
      void el.offsetWidth;
      el.classList.add('pulse-copy');
      setTimeout(() => el.classList.remove('pulse-copy'), 380);
    }
  });

  if (itemsToCopy.length === 1) {
    const label = previewText(itemsToCopy[0].text || itemsToCopy[0].id, 14);
    toast(`已複製物件「${label}」`, 'success');
  } else {
    toast(`已複製 ${itemsToCopy.length} 個物件`, 'success');
  }
}

function pasteObjects() {
  if (!state.clipboard || !Array.isArray(state.clipboard) || state.clipboard.length === 0) {
    toast('剪貼簿是空的', '');
    return;
  }

  const pIdx = state.selectedPageIndex;
  const pStr = String(pIdx);
  if (!state.customEdits[pStr]) state.customEdits[pStr] = {};

  pushUndo();

  const natW = state.canvasNaturalSize.width || 1920;
  const natH = state.canvasNaturalSize.height || 1080;
  const offset = 24;
  const newSelectedIds = [];

  state.clipboard.forEach((clipItem, idx) => {
    const newId = `custom_text_${Date.now().toString(36)}_${idx}`;
    const copy = JSON.parse(JSON.stringify(clipItem));
    copy.id = newId;
    copy.mode = 'wordart'; // 貼上均為文字藝術師
    copy.x = Math.max(0, Math.min(natW - copy.width, copy.x + offset));
    copy.y = Math.max(0, Math.min(natH - copy.height, copy.y + offset));
    copy.deleted = false;

    state.customEdits[pStr][newId] = copy;
    newSelectedIds.push(newId);
  });

  renderInteractiveOverlay(pIdx);
  renderSidebarList(pIdx);

  state.selectedObjIds = newSelectedIds;
  state.selectedObjId = newSelectedIds[0];
  syncSelectionClasses();

  if (newSelectedIds.length === 1) {
    openInspector(newSelectedIds[0]);
  } else {
    openMultiInspector();
  }

  markDirty();

  newSelectedIds.forEach((id) => {
    const el = document.getElementById(`canvas-item-${id}`);
    if (el) {
      el.classList.add('pop-paste');
      setTimeout(() => el.classList.remove('pop-paste'), 300);
    }
  });

  toast(`已貼上 ${newSelectedIds.length} 個物件`, 'success');
}

function deleteSelectedObjects() {
  const ids = state.selectedObjIds.length > 0 ? state.selectedObjIds : (state.selectedObjId ? [state.selectedObjId] : []);
  if (ids.length === 0) return;

  pushUndo();
  const pIdx = state.selectedPageIndex;

  ids.forEach((id) => {
    const edit = getObjectEdit(pIdx, id);
    if (edit) edit.deleted = true;
  });

  deselectObject();
  renderInteractiveOverlay(pIdx);
  renderSidebarList(pIdx);
  markDirty();
  toast(`已刪除 ${ids.length} 個物件`, '');
}

function moveSelectedObjects(dx, dy) {
  const ids = state.selectedObjIds.length > 0 ? state.selectedObjIds : (state.selectedObjId ? [state.selectedObjId] : []);
  if (ids.length === 0) return;

  pushUndo();
  const pIdx = state.selectedPageIndex;
  const natW = state.canvasNaturalSize.width || 1920;
  const natH = state.canvasNaturalSize.height || 1080;

  ids.forEach((id) => {
    const edit = getObjectEdit(pIdx, id);
    if (edit) {
      edit.x = Math.max(0, Math.min(natW - edit.width, edit.x + dx));
      edit.y = Math.max(0, Math.min(natH - edit.height, edit.y + dy));
      const el = document.getElementById(`canvas-item-${id}`);
      if (el) updateCanvasItemStyle(el, edit, natW, natH);
    }
  });

  if (state.selectedObjId) {
    const primary = getObjectEdit(pIdx, state.selectedObjId);
    if (primary) updateInspectorPosition(primary);
  }
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
  if (state.selectedObjIds.length > 1) {
    openMultiInspector();
  } else if (state.selectedObjId) {
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

// ── Global Keyboard Shortcuts (Escape 取消拖曳 / 縮放 / 旋轉 / 選取) ────────
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

  // Esc: 若正在拖曳/縮放/旋轉則取消操作還原；否則取消選取
  if (e.key === 'Escape') {
    if (state.activeInteraction && typeof state.activeInteraction.cancel === 'function') {
      e.preventDefault();
      state.activeInteraction.cancel();
      state.activeInteraction = null;
      toast('已取消本次調整', '');
      return;
    }
    if ((state.selectedObjIds.length > 0 || state.selectedObjId) && !isTyping) {
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
    copySelectedObjects();
    return;
  }

  // Ctrl+V: Paste
  if (isCtrl && e.code === 'KeyV') {
    e.preventDefault();
    pasteObjects();
    return;
  }

  // Ctrl+S: Save Draft
  if (isCtrl && e.code === 'KeyS') {
    e.preventDefault();
    if (state.isDirty) saveCustomEdits();
    return;
  }

  // Delete / Backspace: Delete selected objects
  if ((e.key === 'Delete' || e.key === 'Backspace') && (state.selectedObjIds.length > 0 || state.selectedObjId)) {
    e.preventDefault();
    deleteSelectedObjects();
    return;
  }

  // 方向鍵: 微調物件位置 (Shift 為 10px)
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) && (state.selectedObjIds.length > 0 || state.selectedObjId)) {
    e.preventDefault();
    const step = e.shiftKey ? 10 : 1;
    let dx = 0, dy = 0;
    if (e.key === 'ArrowLeft') dx = -step;
    if (e.key === 'ArrowRight') dx = step;
    if (e.key === 'ArrowUp') dy = -step;
    if (e.key === 'ArrowDown') dy = step;
    moveSelectedObjects(dx, dy);
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

async function autoRestoreLastJob() {
  const urlParams = new URLSearchParams(window.location.search);
  let targetJobId = urlParams.get('job_id');
  if (!targetJobId) {
    try {
      const res = await fetch(`${API}/api/jobs`);
      if (res.ok) {
        const data = await res.json();
        if (data.jobs && data.jobs.length > 0) {
          targetJobId = data.jobs[0].job_id;
        }
      }
    } catch (e) {
      console.warn('Failed to fetch existing jobs list:', e);
    }
  }

  if (targetJobId) {
    try {
      await loadResult(targetJobId);
      history.replaceState(null, '', `?job_id=${targetJobId}`);
    } catch (e) {
      console.warn('Auto restore job failed:', e);
    }
  }
}

document.body.setAttribute('aria-busy', 'false');
loadCapabilities().then(() => {
  autoRestoreLastJob();
});
syncDisabledControls();
