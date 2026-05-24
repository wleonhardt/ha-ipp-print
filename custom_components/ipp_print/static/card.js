// Lovelace card that picks a PDF and POSTs it to /api/ipp_print/print
// with the user's HA bearer token. No iframe, no Media Browser, no ingress.
//
// Type:  custom:ipp-print-upload-card
// Options:
//   title:  string, default "Print PDF"
//
// IMPORTANT: customElements.define() is at line ~10 — register the tag as
// early as possible so HA's lovelace card factory can resolve `custom:` cards
// without timing out on slow connections (Firefox / mobile). The method bodies
// are attached to the prototype below, after the registration call. Lovelace
// only needs the tag to exist; once it does, `setConfig`/`hass`/`connectedCallback`
// will resolve via prototype lookup even if they're patched onto the prototype
// "later" in the same script.

const TAG = 'ipp-print-upload-card';

if (!customElements.get(TAG)) {
  customElements.define(TAG, class extends HTMLElement {});
}

const C = customElements.get(TAG);

C.prototype.setConfig = function (config) {
  this._config = Object.assign({ title: 'Print PDF' }, config || {});
  this._render();
};

// hass is set every state update; keep the latest reference for the token.
Object.defineProperty(C.prototype, 'hass', {
  set(hass) { this._hass = hass; },
  configurable: true,
});

C.prototype.getCardSize = function () { return 2; };

C.prototype._render = function () {
  if (this._rendered) return;
  const root = this.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      :host { display: block; }
      ha-card {
        padding: 22px 18px;
        border-radius: 18px;
        height: 130px;
        background: rgba(110,231,183,0.18);
        border: 1px solid rgba(110,231,183,0.55);
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        gap: 8px;
        cursor: pointer;
        transition: transform .08s ease, background .15s ease;
        box-sizing: border-box;
      }
      ha-card:hover { background: rgba(110,231,183,0.26); }
      ha-card:active { transform: scale(.99); }
      ha-card.busy { cursor: progress; opacity: .85; }
      .icon { width: 36px; height: 36px; color: #7be7c0; flex-shrink: 0; }
      .title { font-weight: 700; font-size: 20px; color: var(--primary-text-color, #fff); line-height: 1; }
      .status { font-size: 13px; min-height: 16px; color: var(--secondary-text-color, rgba(255,255,255,0.75)); text-align: center; padding: 0 8px; }
      .status.err { color: #fca5a5; }
      .status.ok  { color: #6ee7b7; }
      .cancel {
        font-size: 11px;
        color: #fca5a5;
        cursor: pointer;
        text-decoration: underline;
        text-underline-offset: 2px;
        margin-top: -4px;
        display: none;
      }
      .cancel.show { display: inline; }
      .cancel:hover { color: #fecaca; }
    </style>
    <ha-card role="button" tabindex="0">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/>
        <line x1="12" y1="3" x2="12" y2="15"/>
      </svg>
      <div class="title"></div>
      <div class="status" aria-live="polite"></div>
      <div class="cancel" role="button" tabindex="0">Cancel</div>
    </ha-card>
  `;
  this._card = root.querySelector('ha-card');
  this._titleEl = root.querySelector('.title');
  this._statusEl = root.querySelector('.status');
  this._cancelEl = root.querySelector('.cancel');
  this._titleEl.textContent = this._config.title;

  // Card click → file picker; but cancel button intercepts its own clicks.
  this._card.addEventListener('click', (ev) => {
    if (ev.target === this._cancelEl) return;
    this._pick();
  });
  this._card.addEventListener('keydown', (ev) => {
    if (ev.target === this._cancelEl) return;
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      this._pick();
    }
  });
  this._cancelEl.addEventListener('click', (ev) => {
    ev.stopPropagation();
    this._cancelJob();
  });
  this._cancelEl.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      ev.stopPropagation();
      this._cancelJob();
    }
  });
  this._rendered = true;
};

C.prototype._cancelJob = async function () {
  if (this._activeJobId == null) return;
  const token =
    this._hass?.auth?.data?.access_token ||
    this._hass?.connection?.auth?.data?.access_token ||
    null;
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    const r = await fetch('/api/ipp_print/cancel', {
      method: 'POST',
      headers,
      body: JSON.stringify({ job_id: this._activeJobId }),
      credentials: 'same-origin',
    });
    if (!r.ok) {
      const body = await r.text();
      this._setStatus('Cancel failed: ' + body.slice(0, 80), 'err');
      return;
    }
    this._setStatus('Cancelling…');
    // The coordinator's next poll will observe IPP terminal state and the
    // sensor subscription will overwrite this with "Print canceled".
  } catch (err) {
    this._setStatus('Cancel failed: ' + (err?.message || err), 'err');
  }
};

C.prototype._setCancelVisible = function (visible) {
  if (!this._cancelEl) return;
  this._cancelEl.classList.toggle('show', !!visible);
};

C.prototype._setStatus = function (text, cls = '') {
  this._statusEl.textContent = text || '';
  this._statusEl.className = 'status' + (cls ? ' ' + cls : '');
};

C.prototype._pick = function () {
  if (this._busy) return;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'application/pdf,.pdf';
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (!file) {
      this._setStatus('Choose a PDF first.', 'err');
      return;
    }
    this._upload(file);
  });
  input.click();
};

C.prototype._upload = async function (file) {
  if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
    this._setStatus('Pick a .pdf file.', 'err');
    return;
  }
  this._busy = true;
  this._card.classList.add('busy');
  this._setStatus('Uploading…');

  const form = new FormData();
  form.append('file', file, file.name);

  const token =
    this._hass?.auth?.data?.access_token ||
    this._hass?.connection?.auth?.data?.access_token ||
    this._hass?.auth?.accessToken ||
    null;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  try {
    // New direct-IPP endpoint. Returns a real printer-assigned job-id we can
    // track via sensor.printer_current_job. /upload was the legacy
    // filesystem-queue path and is still wired up but unused.
    const resp = await fetch('/api/ipp_print/print', {
      method: 'POST',
      body: form,
      headers,
      credentials: 'same-origin',
    });
    let body = null;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      try { body = await resp.json(); } catch { /* keep null */ }
    }
    if (!resp.ok) {
      const msg = (body && (body.message || body.error)) || `HTTP ${resp.status}`;
      throw new Error(msg);
    }
    const name = (body && body.filename) || file.name;
    this._activeJobId = body?.job_id ?? null;
    this._setStatus(`Submitted ✓ ${name}`, 'ok');
    // Subscribe to printer_current_job updates for this job-id.
    this._trackPrintProgress().catch((e) => {
      console.warn('[ipp-print] progress tracking error', e);
    });
  } catch (err) {
    this._setStatus('Submit failed: ' + (err && err.message ? err.message : err), 'err');
  } finally {
    this._busy = false;
    this._card.classList.remove('busy');
  }
};

// Phase 3: subscribe to sensor.printer_current_job directly. The integration's
// coordinator polls IPP every 1.5s and pushes real per-job state through this
// sensor's attributes, so we no longer need to infer printing activity from
// the HP integration's lifetime counters.
const JOB_SENSOR = 'sensor.printer_current_job';
const TERMINAL_STATES = new Set([
  'canceled', 'aborted', 'completed',
]);
const ACTIVE_STATES = new Set([
  'pending', 'pending-held', 'processing', 'processing-stopped',
]);

C.prototype._trackPrintProgress = async function () {
  const hass = this._hass;
  if (!hass || !hass.connection) return;

  // Cancel any previous subscription so successive uploads don't overlap.
  if (this._unsubProgress) {
    try { this._unsubProgress(); } catch {}
    this._unsubProgress = null;
  }
  clearTimeout(this._progressSafety);

  const ourJobId = this._activeJobId;
  let sawState = null;

  const render = (state, attrs) => {
    const pagesDone = attrs?.pages_done;
    const pagesTotal = attrs?.pages_total;
    let msg;
    if (state === 'processing') {
      if (pagesTotal && pagesDone != null) {
        msg = `Printing page ${pagesDone}/${pagesTotal}…`;
      } else if (pagesDone) {
        msg = `Printing page ${pagesDone}…`;
      } else {
        msg = 'Printing…';
      }
      this._setStatus(msg);
      this._setCancelVisible(true);
    } else if (state === 'pending' || state === 'pending-held') {
      this._setStatus('Queued for printer…');
      this._setCancelVisible(true);
    } else if (state === 'completed') {
      const pages = pagesDone || pagesTotal;
      const pagesMsg = pages ? ` (${pages} page${pages > 1 ? 's' : ''})` : '';
      this._setStatus(`Print complete ✓${pagesMsg}`, 'ok');
      this._setCancelVisible(false);
    } else if (state === 'canceled') {
      this._setStatus('Print canceled', 'err');
      this._setCancelVisible(false);
    } else if (state === 'aborted') {
      const reason = attrs?.state_reasons;
      this._setStatus(
        'Print failed' + (reason ? `: ${reason}` : ''),
        'err',
      );
      this._setCancelVisible(false);
    } else {
      this._setCancelVisible(false);
    }
  };

  // Push the initial render from the current sensor snapshot — the
  // coordinator may have already moved the job into pending before we
  // subscribed.
  const initial = hass.states[JOB_SENSOR];
  if (initial && initial.attributes?.job_id === ourJobId) {
    sawState = initial.state;
    render(initial.state, initial.attributes);
  }

  this._unsubProgress = await hass.connection.subscribeEvents((ev) => {
    if (ev?.data?.entity_id !== JOB_SENSOR) return;
    const newState = ev.data.new_state;
    if (!newState) return;
    // Only act on changes that belong to our job, or to idle (which means the
    // coordinator cleared after the terminal hold window).
    const attrs = newState.attributes || {};
    const sensorJobId = attrs.job_id;
    if (sensorJobId != null && sensorJobId !== ourJobId) return;
    sawState = newState.state;
    render(newState.state, attrs);
    if (TERMINAL_STATES.has(newState.state)) {
      // Leave the message up for a bit, then unsubscribe.
      clearTimeout(this._progressSafety);
      this._progressSafety = setTimeout(() => {
        if (this._statusEl?.textContent &&
            !ACTIVE_STATES.has(sawState)) {
          this._setStatus('');
        }
      }, 10_000);
      try { this._unsubProgress(); } catch {}
      this._unsubProgress = null;
    }
  }, 'state_changed');

  // Safety net: if no events arrive for 90 seconds, clean up.
  this._progressSafety = setTimeout(() => {
    if (this._unsubProgress) {
      try { this._unsubProgress(); } catch {}
      this._unsubProgress = null;
    }
    if (!sawState) {
      this._setStatus('Job submitted (no further updates)', 'ok');
      setTimeout(() => {
        if (this._statusEl?.textContent?.startsWith('Job submitted')) {
          this._setStatus('');
        }
      }, 6000);
    }
  }, 90_000);
};

window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: 'LJ Printer Upload',
    description: 'Authenticated PDF upload to /media/print_inbox (no ingress, no Media Browser).',
    preview: false,
  });
}

// Self-healing for HA's whenDefined() race. On slow loads (Firefox/mobile),
// lovelace can render `hui-error-card` "Configuration error" placeholders
// for our card before this script finishes loading. Once we're running, walk
// the DOM, find any error cards whose config points at our tag, and swap in
// a real instance.
function _ljpHeal() {
  const root = document.querySelector('home-assistant');
  if (!root) return;
  const stack = [root];
  const errors = [];
  while (stack.length) {
    const el = stack.pop();
    if (!el) continue;
    if (el.tagName === 'HUI-ERROR-CARD') errors.push(el);
    if (el.shadowRoot) stack.push(el.shadowRoot);
    for (const c of (el.children || [])) stack.push(c);
  }
  for (const err of errors) {
    const cfg = err._config || err.config;
    if (!cfg || cfg.type !== 'custom:' + TAG) continue;
    const fresh = document.createElement(TAG);
    fresh.setConfig(cfg);
    err.replaceWith(fresh);
  }
}
// Retry across several timings — covers fast loads (50ms) and slow phones (2s+).
[60, 250, 800, 2000, 5000].forEach((ms) => setTimeout(_ljpHeal, ms));
