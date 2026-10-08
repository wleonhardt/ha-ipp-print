// Lovelace card that picks a PDF/JPEG/PNG and POSTs it to /api/ipp_print/print
// with the user's HA bearer token. No iframe, no Media Browser, no ingress.
//
// Type:  custom:ipp-print-upload-card
// Options:
//   title:   string, default "Print"
//   entity:  job sensor of the printer to print to. Optional with one
//            printer configured; required once there are several.
//
// IMPORTANT: customElements.define() is at line ~10 — register the tag as
// early as possible so HA's lovelace card factory can resolve `custom:` cards
// without timing out on slow connections (Firefox / mobile). The method bodies
// are attached to the prototype below, after the registration call. Lovelace
// only needs the tag to exist; once it does, `setConfig`/`hass`/`connectedCallback`
// will resolve via prototype lookup even if they're patched onto the prototype
// "later" in the same script.

const TAG = 'ipp-print-upload-card';
const ACCEPTED_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png']);

if (!customElements.get(TAG)) {
  // Lifecycle callbacks are captured at define(), unlike ordinary methods.
  // Forward them so the implementation can still follow early registration.
  customElements.define(TAG, class extends HTMLElement {
    connectedCallback() { this._connected?.(); }
    disconnectedCallback() { this._disconnected?.(); }
  });
}

const C = customElements.get(TAG);

C.getStubConfig = function () { return { title: 'Print' }; };

C.prototype.setConfig = function (config) {
  this._config = Object.assign({ title: 'Print' }, config || {});
  this._render();
  // _render is one-shot; apply config changes (card editor) directly.
  if (this._titleEl) this._titleEl.textContent = this._config.title;
};

// hass is set every state update; keep the latest reference for the token.
Object.defineProperty(C.prototype, 'hass', {
  set(hass) { this._hass = hass; },
  configurable: true,
});

C.prototype.getCardSize = function () { return 3; };
C.prototype.getGridOptions = function () { return { columns: 6, rows: 4, min_columns: 6, min_rows: 4 }; };

C.prototype._render = function () {
  if (this._rendered) return;
  const root = this.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      /* Shared document-card contract v1. Keep this base identical in both cards. */
      :host { display: block; height: 100%; }
      [hidden] { display: none !important; }
      ha-card {
        box-sizing: border-box; height: 100%; min-height: 200px; padding: 12px;
        display: flex; flex-direction: column; gap: 8px;
        color: var(--primary-text-color);
      }
      .header { display: flex; align-items: center; gap: 8px; min-width: 0; }
      .icon { --mdc-icon-size: 24px; width: 24px; height: 24px; color: var(--primary-color); flex: none; }
      .title { font-size: 16px; font-weight: 500; line-height: 24px; overflow-wrap: anywhere; }
      .status { color: var(--secondary-text-color); font-size: 14px; line-height: 20px; min-height: 40px; overflow-wrap: anywhere; }
      .status.err { color: var(--error-color); }
      .status.ok { color: var(--success-color, var(--primary-color)); }
      .status a { color: inherit; text-underline-offset: 2px; display: inline-flex; align-items: center; min-height: 44px; }
      .status summary { cursor: pointer; min-height: 44px; }
      .status details > div { padding-top: 8px; }
      .controls { min-height: 44px; }
      .actions { margin-top: auto; }
      button, select { font: inherit; font-size: 14px; }
      button {
        min-height: 44px; padding: 8px 12px; border: 0;
        border-radius: var(--ha-card-border-radius, 12px);
        background: var(--secondary-background-color); color: var(--primary-text-color);
        cursor: pointer; line-height: 20px; box-sizing: border-box;
      }
      button:disabled { opacity: .5; cursor: default; }
      button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, a:focus-visible {
        outline: 2px solid var(--primary-color); outline-offset: 2px;
      }
      .primary, .cancel { width: 100%; font-weight: 500; }
      .cancel { display: none; color: var(--error-color); }
      .cancel.show { display: block; }
      @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
      /* End shared document-card base. */
      .file-name { font-size: 14px; line-height: 20px; color: var(--secondary-text-color); overflow-wrap: anywhere; }
      .file-actions { display: flex; gap: 8px; margin-top: 8px; }
      .file-actions button { flex: 1; min-width: 0; padding: 8px 4px; }
    </style>
    <ha-card>
      <div class="header"><ha-icon class="icon" icon="mdi:printer" aria-hidden="true"></ha-icon><div class="title"></div></div>
      <div class="status" aria-live="polite" aria-atomic="true"></div>
      <div class="controls">
        <div class="file-name"></div>
        <div class="file-actions" hidden><button class="replace" type="button">Replace</button><button class="clear" type="button">Clear</button></div>
      </div>
      <div class="actions">
        <button class="primary" type="button">Choose file</button>
        <button class="cancel" type="button">Cancel print</button>
      </div>
    </ha-card>
  `;
  this._card = root.querySelector('ha-card');
  this._titleEl = root.querySelector('.title');
  this._statusEl = root.querySelector('.status');
  this._cancelEl = root.querySelector('.cancel');
  this._primaryEl = root.querySelector('.primary');
  this._fileNameEl = root.querySelector('.file-name');
  this._fileActionsEl = root.querySelector('.file-actions');
  this._titleEl.textContent = this._config.title;
  this._primaryEl.addEventListener('click', () => {
    if (this._stagedFile) this._upload(this._stagedFile);
    else this._pick();
  });
  this._cancelEl.addEventListener('click', () => this._cancelJob());
  root.querySelector('.replace').addEventListener('click', () => this._pick());
  root.querySelector('.clear').addEventListener('click', () => {
    if (this._busy || this._activeJobId != null) return;
    this._stagedFile = null;
    this._setStatus('');
    this._syncControls();
  });
  this._rendered = true;
  this._setStatus('');
  this._syncControls();
};

C.prototype._syncControls = function () {
  if (!this._primaryEl) return;
  const locked = !!this._busy || this._activeJobId != null;
  this._primaryEl.disabled = locked;
  this._primaryEl.hidden = !!this._showCancel;
  this._primaryEl.textContent = this._busy ? 'Submitting…'
    : this._activeJobId != null ? 'Printing…' : this._stagedFile ? 'Print' : 'Choose file';
  this._fileNameEl.textContent = this._stagedFile?.name || this._jobFilename || 'PDF or image';
  this._fileActionsEl.hidden = !this._stagedFile || locked;
  for (const button of this._fileActionsEl.querySelectorAll('button')) button.disabled = locked;
};

function fileError(file) {
  if (!file) return 'Choose a file first.';
  if (file.size > 50 * 1024 * 1024) return 'File exceeds the 50 MiB limit.';
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name) && !ACCEPTED_TYPES.has(file.type)) {
    return 'Pick a PDF, JPEG, or PNG file.';
  }
  return null;
}

C.prototype._stageFile = function (file) {
  if (this._busy || this._activeJobId != null) return;
  const error = fileError(file);
  if (error) { this._setStatus(error, 'err'); return; }
  this._stopProgress();
  this._stagedFile = file;
  this._jobFilename = null;
  this._setStatus('Ready to print');
  this._syncControls();
};

// Self-healed instances may never receive `hass` from lovelace (the parent
// hui-card can keep pointing at the replaced error card), so every consumer
// falls back to the app root's live hass object.
C.prototype._getHass = function () {
  return document.querySelector('home-assistant')?.hass || this._hass || null;
};

// hass.fetchWithAuth refreshes an expired token automatically; a raw fetch
// with a copied bearer token is the fallback for exotic auth setups.
C.prototype._authedFetch = function (path, init) {
  const hass = this._getHass();
  if (hass?.fetchWithAuth) return hass.fetchWithAuth(path, init);
  const token =
    hass?.auth?.data?.access_token ||
    hass?.connection?.auth?.data?.access_token ||
    hass?.auth?.accessToken ||
    null;
  const headers = Object.assign({}, init?.headers || {});
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(path, Object.assign({}, init, {
    headers,
    credentials: 'same-origin',
  }));
};

// The job sensor doubles as the printer selector for the endpoints. With no
// `entity:` configured, find the integration's sensors in the entity
// registry (hass.entities is available to non-admins too) and use the only
// one; several means the user must pick. Legacy installs keep
// sensor.printer_current_job in the registry, so it is found the same way.
C.prototype._sensorId = function () {
  if (this._config?.entity) return this._config.entity;
  const hass = this._getHass();
  const ids = Object.values(hass?.entities || {})
    .filter((e) => e.platform === 'ipp_print' && e.entity_id.startsWith('sensor.'))
    .map((e) => e.entity_id);
  if (ids.length === 1) return ids[0];
  if (ids.length === 0 && hass?.states?.['sensor.printer_current_job']) {
    return 'sensor.printer_current_job';
  }
  if (ids.length > 1) {
    throw new Error('several printers configured; set entity: on the card');
  }
  return null;
};

C.prototype._cancelJob = async function () {
  if (this._activeJobId == null) return;
  const jobId = this._activeJobId;
  const generation = this._progressGeneration;
  if (this._cancelPending?.jobId === jobId && this._cancelPending?.generation === generation) return;
  const pending = { jobId, generation };
  this._cancelPending = pending;
  try {
    const r = await this._authedFetch('/api/ipp_print/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: jobId, entity_id: this._activeSensorId,
      }),
    });
    if (this._activeJobId !== jobId || this._progressGeneration !== generation) return;
    if (!r.ok) {
      const body = await r.text();
      this._setStatus('Cancel failed: ' + body.slice(0, 80), 'err');
      return;
    }
    this._setStatus('Cancelling…');
    // The coordinator's next poll will observe IPP terminal state and the
    // sensor subscription will overwrite this with "Print canceled".
  } catch (err) {
    if (this._activeJobId === jobId && this._progressGeneration === generation) {
      this._setStatus('Cancel failed: ' + (err?.message || err), 'err');
    }
  } finally {
    if (this._cancelPending === pending) this._cancelPending = null;
  }
};

C.prototype._setCancelVisible = function (visible) {
  if (!this._cancelEl) return;
  this._showCancel = !!visible;
  this._cancelEl.classList.toggle('show', !!visible);
  this._syncControls();
};

C.prototype._setStatus = function (text, cls = '') {
  this._statusEl.textContent = text || (this._stagedFile ? 'Ready to print' : 'Choose a document');
  this._statusEl.className = 'status' + (cls ? ' ' + cls : '');
};

C.prototype._pick = function () {
  if (this._busy || this._activeJobId != null) return;
  this._cleanupPicker?.();
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png';
  // CRITICAL: the input must be attached to the document for the `change`
  // event to fire reliably across modern browsers. A detached `<input>`
  // silently swallows the event in current Chrome / Safari builds — the
  // user sees the file picker, selects a file, the picker closes, and
  // nothing happens. Insert it hidden, then clean up after pick/cancel.
  input.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0;pointer-events:none;width:0;height:0;';
  document.body.appendChild(input);
  let timer;
  const cleanup = () => {
    clearTimeout(timer);
    input.remove();
    if (this._cleanupPicker === cleanup) this._cleanupPicker = null;
  };
  this._cleanupPicker = cleanup;
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    cleanup();
    if (file) this._stageFile(file);
  }, { once: true });
  // Safety net: if the user cancels the picker, modern browsers fire
  // `cancel` (and no `change`). Clean up so we don't leak inputs.
  input.addEventListener('cancel', cleanup, { once: true });
  // Last-resort GC: if neither event fires within 5 minutes, drop the input.
  timer = setTimeout(cleanup, 5 * 60 * 1000);
  input.click();
};

C.prototype._upload = async function (file) {
  if (this._busy || this._activeJobId != null) return;
  const error = fileError(file);
  if (error) { this._setStatus(error, 'err'); return; }
  let sensorId;
  try {
    sensorId = this._sensorId();
  } catch (err) {
    this._setStatus(err.message, 'err');
    return;
  }
  this._stopProgress();
  this._activeJobId = null;
  this._setCancelVisible(false);
  this._busy = true;
  this._card.classList.add('busy');
  this._setStatus('Uploading…');
  this._cleanupPicker?.();
  this._syncControls();

  const form = new FormData();
  if (sensorId) form.append('entity_id', sensorId);
  form.append('file', file, file.name);

  let definitelyRejected = false;
  try {
    // Returns the printer-assigned job-id we then track via the job sensor.
    const resp = await this._authedFetch('/api/ipp_print/print', {
      method: 'POST',
      body: form,
    });
    let body = null;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      try { body = await resp.json(); } catch { /* keep null */ }
    }
    if (!resp.ok) {
      definitelyRejected = resp.status >= 400 && resp.status < 500 && resp.status !== 408;
      const msg = [body?.message, body?.error].find(value => typeof value === 'string' && value.trim());
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    if (!Number.isInteger(body?.job_id) || body.job_id <= 0) {
      throw new Error('The printer did not return a valid job number.');
    }
    const name = typeof body.filename === 'string' && body.filename ? body.filename : file.name;
    this._stagedFile = null;
    this._jobFilename = name;
    this._activeJobId = body?.job_id ?? null;
    this._activeSensorId = sensorId;
    this._setCancelVisible(true);
    this._setStatus(`Submitted ✓ ${name}`, 'ok');
    // Subscribe to the job sensor's updates for this job-id.
    this._trackPrintProgress(sensorId).catch((e) => {
      console.warn('[ipp-print] progress tracking error', e);
      if (this._activeJobId === body?.job_id) {
        this._setStatus('Job submitted (progress unavailable)', 'ok');
      }
    });
  } catch (err) {
    if (!definitelyRejected) this._stagedFile = null;
    const guidance = definitelyRejected ? '' : ' Check the printer queue before choosing the file again; it may already have printed.';
    this._setStatus('Submit failed: ' + (err?.message || err) + guidance, 'err');
  } finally {
    this._busy = false;
    this._card.classList.remove('busy');
    this._syncControls();
  }
};

// The integration's coordinator polls IPP every 1.5s and pushes per-job
// state through the job sensor's state + attributes; the card follows it.
const TERMINAL_STATES = new Set([
  'canceled', 'aborted', 'completed', 'unknown',
]);
const ACTIVE_STATES = new Set([
  'pending', 'pending-held', 'processing', 'processing-stopped',
]);

C.prototype._stopProgress = function () {
  this._progressGeneration = (this._progressGeneration || 0) + 1;
  clearTimeout(this._progressSafety);
  if (this._unsubProgress) {
    try { this._unsubProgress(); } catch {}
    this._unsubProgress = null;
  }
};

C.prototype._disconnected = function () {
  this._cleanupPicker?.();
  this._stopProgress();
};

C.prototype._connected = function () {
  if (this._activeJobId != null && this._activeSensorId) {
    this._trackPrintProgress(this._activeSensorId).catch((err) => {
      console.warn('[ipp-print] progress tracking error', err);
    });
  }
};

C.prototype._trackPrintProgress = async function (sensorId) {
  this._stopProgress();
  const hass = this._getHass();
  const ourJobId = this._activeJobId;
  if (!this.isConnected || !hass?.connection || !sensorId || ourJobId == null) return;

  const generation = this._progressGeneration;
  let stopped = false;
  let unsubscribe = null;
  let sawMatchingState = false;
  const isCurrent = () => generation === this._progressGeneration && this.isConnected;
  const stop = () => {
    stopped = true;
    if (unsubscribe) { try { unsubscribe(); } catch {} }
    if (isCurrent()) {
      this._unsubProgress = null;
      clearTimeout(this._progressSafety);
      this._activeJobId = null;
      this._setCancelVisible(false);
    }
  };
  const render = (state, attrs) => {
    const pagesDone = attrs?.pages_done;
    const pagesTotal = attrs?.pages_total;
    if (state === 'processing') {
      const progress = pagesTotal && pagesDone != null
        ? ` page ${pagesDone}/${pagesTotal}` : pagesDone ? ` page ${pagesDone}` : '';
      this._setStatus(`Printing${progress}…`);
    } else if (state === 'pending' || state === 'pending-held') {
      this._setStatus('Queued for printer…');
    } else if (state === 'processing-stopped') {
      this._setStatus('Printing paused' + (attrs?.state_reasons ? `: ${attrs.state_reasons}` : ''));
    } else if (state === 'completed') {
      const pages = pagesDone ?? pagesTotal;
      const pagesMsg = pages ? ` (${pages} page${pages > 1 ? 's' : ''})` : '';
      this._setStatus(`Print complete ✓${pagesMsg}`, 'ok');
    } else if (state === 'canceled') {
      this._setStatus('Print canceled', 'err');
    } else if (state === 'aborted') {
      this._setStatus('Print failed' + (attrs?.state_reasons ? `: ${attrs.state_reasons}` : ''), 'err');
    } else if (state === 'unknown') {
      this._setStatus('Print outcome unknown (printer removed job)', 'err');
    }
    this._setCancelVisible(ACTIVE_STATES.has(state));
  };

  const initial = hass.states?.[sensorId];
  const cur = {
    state: initial?.state ?? null,
    attributes: Object.assign({}, initial?.attributes || {}),
  };
  const onUpdate = () => {
    if (stopped || !isCurrent()) return;
    if (cur.attributes.job_id !== ourJobId) {
      if (sawMatchingState) {
        sawMatchingState = false;
        this._setStatus('Job submitted (printer is tracking another job)', 'ok');
        this._setCancelVisible(false);
        this._progressSafety = setTimeout(() => {
          if (isCurrent() && !stopped) stop();
        }, 90_000);
      }
      return;
    }
    sawMatchingState = true;
    clearTimeout(this._progressSafety);
    render(cur.state, cur.attributes);
    if (TERMINAL_STATES.has(cur.state)) {
      stop();
      this._activeJobId = null;
      this._progressSafety = setTimeout(() => {
        if (isCurrent()) this._setStatus('');
      }, 10_000);
    }
  };
  onUpdate();
  if (stopped) return;

  // Limit the wait for the first matching snapshot. Once an active job is
  // seen, keep listening until terminal state: real print jobs can take
  // much longer than 90 seconds without changing their sensor attributes.
  if (!sawMatchingState) {
    this._progressSafety = setTimeout(() => {
      if (!isCurrent() || stopped) return;
      stop();
      this._setStatus('Job submitted (no further updates)', 'ok');
    }, 90_000);
  }

  try {
    unsubscribe = await hass.connection.subscribeMessage((msg) => {
      if (stopped || !isCurrent()) return;
      if (msg?.r?.includes(sensorId)) {
        stop();
        this._setStatus('Job submitted (printer sensor unavailable)', 'err');
        return;
      }
      const add = msg?.a?.[sensorId];
      if (add) {
        cur.state = add.s;
        cur.attributes = Object.assign({}, add.a || {});
        onUpdate();
        return;
      }
      const chg = msg?.c?.[sensorId];
      if (!chg) return;
      const plus = chg['+'] || {};
      const minus = chg['-'] || {};
      if (plus.s !== undefined) cur.state = plus.s;
      if (plus.a) Object.assign(cur.attributes, plus.a);
      for (const k of (minus.a || [])) delete cur.attributes[k];
      onUpdate();
    }, { type: 'subscribe_entities', entity_ids: [sensorId] });
  } catch (err) {
    if (isCurrent()) stop();
    throw err;
  }
  // Initial subscription messages can arrive before the promise resolves.
  // A terminal update, new upload, or disconnect must close that late handle.
  if (stopped || !isCurrent()) {
    try { unsubscribe(); } catch {}
  } else {
    this._unsubProgress = unsubscribe;
  }
};

window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: 'IPP Print Upload',
    description: 'Upload a PDF or image straight to an IPP printer with live job progress.',
    preview: true,
  });
}

// Self-healing for HA's whenDefined() race. On slow loads (Firefox / mobile /
// slow networks), lovelace can render `hui-error-card` "Configuration error"
// placeholders for our card before this script finishes loading. Once we're
// running, walk the DOM, find any error cards whose config points at our
// tag, and swap in a real instance.
//
// Recent HA changed the hui-error-card config shape: the err's own _config
// is now {type: 'error', message: 'Custom element doesn\'t exist...'} rather
// than the user-provided config. The original lives on the parent <hui-card>
// under _elementConfig. We source from there first and fall back gracefully.
const _LJP_HEALED = new WeakSet();

function _ljpHealOne(err) {
  if (_LJP_HEALED.has(err)) return;
  const parent = err.parentElement;
  let cfg = parent && parent._elementConfig;
  if (!cfg) cfg = err._config || err.config;
  if (!cfg || cfg.type !== 'custom:' + TAG) {
    // Last resort: parse the missing tag from the error message and build
    // a default config so the dashboard isn't stuck on "Configuration error".
    const msg = err._config && err._config.message;
    if (typeof msg === 'string' && msg.indexOf(TAG) !== -1) {
      cfg = {type: 'custom:' + TAG};
    } else {
      return;
    }
  }
  _LJP_HEALED.add(err);
  // Let HA rebuild its owned element, not just the DOM node. Otherwise it
  // keeps pushing hass to the error and may reinsert it on visibility updates.
  if (parent?.tagName === 'HUI-CARD' && parent._element === err
      && parent.config?.type === 'custom:' + TAG && typeof parent.load === 'function') {
    try {
      parent.load();
      return;
    } catch {
      _LJP_HEALED.delete(err);
      return;
    }
  }
  // If the parent hui-card already has a real instance of our element
  // (Lovelace's own whenDefined() callback may have inserted one alongside
  // the error card), just remove the error card sibling. Otherwise replace
  // the error card in place with a fresh instance.
  const existing = parent && parent.querySelector
    ? parent.querySelector(TAG)
    : null;
  if (existing) {
    err.remove();
    return;
  }
  const fresh = document.createElement(TAG);
  try {
    fresh.setConfig(cfg);
  } catch (e) {
    return;
  }
  // Lovelace won't push `hass` to a node it didn't create — seed it once
  // here; runtime consumers use _getHass() for a live fallback after this.
  const ha = document.querySelector('home-assistant');
  if (ha && ha.hass) fresh.hass = ha.hass;
  err.replaceWith(fresh);
}

function _ljpHeal() {
  const root = document.querySelector('home-assistant');
  if (!root) return;
  const stack = [root];
  while (stack.length) {
    const el = stack.pop();
    if (!el) continue;
    if (el.tagName === 'HUI-ERROR-CARD') _ljpHealOne(el);
    if (el.shadowRoot) stack.push(el.shadowRoot);
    for (const c of (el.children || [])) stack.push(c);
  }
}
// Staggered retries across the typical timing window.
[40, 120, 300, 700, 1500, 3000, 6000, 10_000].forEach(
  (ms) => setTimeout(_ljpHeal, ms),
);

// Watch for error cards that appear after the initial retry window —
// dashboard navigation, lazy view mounts, etc. Once this script has run,
// customElements.define has succeeded, so "custom element doesn't exist"
// error cards can only come from renders already in flight — disconnect
// after 30s instead of paying the observer cost for the whole session.
try {
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const n of m.addedNodes) {
        if (!n || n.nodeType !== 1) continue;
        if (n.tagName === 'HUI-ERROR-CARD') {
          _ljpHealOne(n);
        } else if (n.querySelectorAll) {
          n.querySelectorAll('hui-error-card').forEach(_ljpHealOne);
        }
      }
    }
  });
  observer.observe(document.body, {childList: true, subtree: true});
  setTimeout(() => { try { observer.disconnect(); } catch {} }, 30_000);
} catch {}
