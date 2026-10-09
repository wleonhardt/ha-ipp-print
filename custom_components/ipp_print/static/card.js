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

const FEATURE_TAG = 'ipp-print-feature';
const FEATURE_DOMAIN = 'ipp_print';
if (!customElements.get(FEATURE_TAG)) {
  customElements.define(FEATURE_TAG, class extends HTMLElement {
    connectedCallback() { this._updateFeature?.(); }
  });
}

const C = customElements.get(TAG);

// BEGIN ENGLISH CATALOG
const CARD_TRANSLATIONS = {
  "en": {
    "feature.config": "Invalid feature configuration.",
    "feature.host_config": "Set the device and title on the parent card.",
    "feature.target": "Select an IPP Print sensor on this card.",
    "feature.bottom": "Set Features position to Bottom to use these controls.",
    "action.options": "Options",
    "action.two_sided": "Two-sided",
    "action.done": "Done",
    "action.canceling": "Cancelling…",
    "choice.automatic": "Automatic",
    "choice.color": "Color",
    "choice.grayscale": "Grayscale",
    "choice.device_default": "Device default",
    "choice.integration_default": "Integration default",
    "choice.long_edge": "Long edge",
    "choice.short_edge": "Short edge",
    "field.color": "Color",
    "editor.title": "Title",
    "editor.duplex_options": "Show Two-sided inside Options",
    "error.retry": "Please try again.",
    "action.print": "Print",
    "action.choose_file": "Choose file",
    "action.cancel": "Cancel print",
    "action.replace": "Replace",
    "action.clear": "Clear",
    "action.submitting": "Submitting…",
    "action.printing": "Printing…",
    "accessibility.two_sided": "Two-sided print",
    "dialog.title": "Print options",
    "config.copies": "Copies must be an integer from 1 to 99.",
    "config.binding": "Invalid two-sided binding.",
    "editor.entity": "Printer sensor (optional)",
    "editor.copies": "Default copies",
    "editor.duplex": "Two-sided by default",
    "editor.binding": "Default binding",
    "field.printer": "Printer",
    "field.copies": "Copies",
    "field.binding": "Two-sided binding",
    "field.paper": "Paper",
    "field.tray": "Tray",
    "field.quality": "Quality",
    "file.hint": "PDF or image",
    "status.ready": "Ready to print",
    "status.choose": "Choose a document",
    "status.uploading": "Uploading…",
    "status.submitted_untracked": "Job submitted (progress unavailable)",
    "status.queued": "Queued for printer…",
    "status.canceled": "Print canceled",
    "status.unknown": "Print outcome unknown. Check the printer queue before printing again.",
    "status.other_job": "Job submitted (printer is tracking another job)",
    "status.no_updates": "Print status unavailable. Check the printer queue before printing again.",
    "status.sensor_unavailable": "Printer job status unavailable. Check the queue before printing again.",
    "error.no_file": "Choose a file first.",
    "error.file_size": "File exceeds the 50 MiB limit.",
    "error.file_type": "Pick a PDF, JPEG, or PNG file.",
    "error.printers": "several printers configured; select one in Options or set entity: on the card",
    "error.changed": "Printer settings changed. Try again.",
    "error.settings": "Selected settings are unavailable. Reset them in Options or check the printer connection.",
    "error.duplex": "Two-sided settings are unavailable. Open Options to check this printer.",
    "error.response": "The printer did not return a valid job number.",
    "error.setting_unavailable": "A selected setting is unavailable for this document. Choose Device default or another supported value.",
    "error.binding": "Choose another binding or turn off Two-sided.",
    "choice.printer": "Select a printer",
    "choice.manual_feed": "Manual feed",
    "choice.bypass": "Bypass tray",
    "choice.main_tray": "Main tray",
    "choice.alternate_tray": "Alternate tray",
    "choice.auto_monochrome": "Auto black and white",
    "choice.monochrome": "Black and white",
    "choice.draft": "Draft",
    "choice.normal": "Normal",
    "choice.best": "Best",
    "paper.letter": "Letter",
    "paper.legal": "Legal",
    "paper.executive": "Executive",
    "paper.ledger": "Ledger",
    "paper.tabloid": "Tabloid",
    "paper.statement": "Statement",
    "paper.foolscap": "Foolscap",
    "paper.oficio": "Oficio",
    "paper.monarch": "Monarch envelope",
    "paper.photo": "Photo",
    "paper.hagaki": "Hagaki postcard",
    "paper.reply": "Reply postcard",
    "paper.min": "Custom minimum",
    "paper.max": "Custom maximum",
    "paper.index": "Index card",
    "help.unavailable": "Choose a printer and file to load settings. Device defaults apply while settings are unavailable.",
    "help.document": "Choose a document to load its paper, tray, color and quality settings.",
    "help.binding": "This printer does not advertise the selected binding. Choose another binding or turn off Two-sided.",
    "picker.name": "IPP Print Upload",
    "picker.description": "Upload a PDF or image straight to an IPP printer with live job progress.",
    "card.title": "Print",
    "status.cancel_failed": "Cancel failed: {error}",
    "editor.help.title": "Leave blank to use the translated card title.",
    "editor.help.entity": "Leave blank to use the only configured device. Select a sensor when more than one printer is available.",
    "editor.help.duplex_in_options": "Move the Two-sided switch into Options to keep the card more compact.",
    "editor.help.copies": "The default is one copy. The printer may advertise a lower maximum.",
    "editor.help.binding": "Long edge flips like a book; short edge flips like a notepad. Applies only to two-sided printing.",
    "editor.help.duplex": "Choose one-sided or two-sided for new print jobs.",
    "config.boolean": "{field} must be true or false.",
    "status.submitted": "Submitted ✓ {name}",
    "status.submit_failed": "Submit failed: {error}{guidance}",
    "help.uncertain": " Check the printer queue before choosing the file again; it may already have printed.",
    "status.printing": "Printing…{progress}",
    "status.page": {"one": " {count} page printed", "other": " {count} pages printed"},
    "status.paused": "Printing paused{reason}",
    "status.complete": {
      "one": "Print complete ✓ ({count} page)",
      "other": "Print complete ✓ ({count} pages)"
    },
    "status.complete_unknown": "Print complete ✓",
    "status.failed": "Print failed{reason}",
    "status.reason": ": {reason}",
    "paper.envelope": "{name} envelope",
    "paper.dimensions": "{name} ({width} × {height} {unit})",
    "help.next_job": "Settings apply to the next print.{loaded}",
    "help.loaded": " Loaded: {paper}.",
    "error.copies_range": "Enter a copy count from 1 to {max}.",
    "status.sheet": {"one": " {count} sheet printed", "other": " {count} sheets printed"},
    "status.complete_sheets": {
      "one": "Print complete ✓ ({count} sheet)",
      "other": "Print complete ✓ ({count} sheets)"
    },
    "connection.ha_lost": "Home Assistant disconnected. Reconnecting…",
    "connection.reachable": "Device reachable",
    "connection.unreachable": "Cannot reach this device. Check its power and connection.",
    "connection.unknown": "Device connection has not been confirmed recently.",
    "connection.checked": "Last checked: {time}"
  }
};
// END ENGLISH CATALOG

// BEGIN DOCUMENT CARD CORE v3
// Canonical source: ha-escl-scan/shared/card-core.js; synchronize with tools/sync-card-core.mjs.
// Shared localization contract v1. Keep this helper identical in both cards.
// Catalogs are bundled here: no build step, translation fetch or registration wait.
class LocalizedMessage {
  constructor(key, values) { this.key = key; this.values = values; }
}
function setText(element, value) {
  if (element.textContent !== value) element.textContent = value;
}
function hasOwn(object, key) { return Object.prototype.hasOwnProperty.call(object, key); }
let lastLanguageValue, lastLanguage = 'en';
function cardLanguage(hass) {
  const value = hass?.locale?.language || hass?.language || 'en';
  if (value === lastLanguageValue) return lastLanguage;
  lastLanguageValue = value;
  try { lastLanguage = Intl.getCanonicalLocales(String(value).replace(/_/g, '-'))[0].toLowerCase(); }
  catch { lastLanguage = 'en'; }
  return lastLanguage;
}
function localize(key, values = {}, hass = document.querySelector('home-assistant')?.hass) {
  const language = cardLanguage(hass);
  for (const locale of new Set([language, language.split('-')[0], 'en'])) {
    const catalog = hasOwn(CARD_TRANSLATIONS, locale) ? CARD_TRANSLATIONS[locale] : null;
    if (!catalog || !hasOwn(catalog, key)) continue;
    let message = catalog[key];
    if (message && typeof message === 'object') {
      const category = new Intl.PluralRules(locale).select(Number(values.count));
      message = hasOwn(message, category) ? message[category] : message.other;
    }
    if (typeof message !== 'string') continue;
    return message.replace(/\{(\w+)\}/g, (token, name) => {
      if (!hasOwn(values, name)) return token;
      const value = values[name];
      return value instanceof LocalizedMessage ? localize(value.key, value.values, hass) : String(value);
    });
  }
  return key;
}
function localizeElements(root, hass) {
  for (const el of root.querySelectorAll('[data-i18n]')) {
    el.textContent = localize(el.dataset.i18n, el._i18nValues || {}, hass);
  }
  for (const el of root.querySelectorAll('[data-i18n-label]')) {
    const label = localize(el.dataset.i18nLabel, {}, hass);
    el.setAttribute('aria-label', label);
    if (el.hasAttribute('title')) el.title = label;
  }
}
function translatedText(key, values = {}, hass) {
  const span = document.createElement('span');
  span.dataset.i18n = key; span._i18nValues = values;
  span.textContent = localize(key, values, hass);
  return span;
}
C.prototype._msg = function (key, values = {}) { return new LocalizedMessage(key, values); };
C.prototype._t = function (key, values) { return localize(key, values, this._hass); };
C.prototype._setMessage = function (key, values = {}, cls = '') {
  this._setStatus(this._t(key, values), cls);
  this._statusMessage = { key, values, cls };
};
C.prototype._applyLanguage = function () {
  if (!this.shadowRoot) return false;
  const language = cardLanguage(this._hass);
  if (language === this._language) return false;
  this._language = language;
  localizeElements(this.shadowRoot, this._hass);
  if (!this._config.title) this._titleEl.textContent = this._t('card.title');
  if (this._statusMessage) {
    const { key, values, cls } = this._statusMessage;
    this._setMessage(key, values, cls);
  }
  return true;
};
// Checked connection is independent of a job's idle/running state.
C.prototype._syncConnection = function () {
  if (!this._connectionEl) return;
  const offline = this._hass?.connected === false;
  const snapshot = this._connectionSnapshot();
  const checked = Date.parse(snapshot?.checked_at);
  const next = Date.parse(snapshot?.next_check_at);
  const fresh = Number.isFinite(checked) && Number.isFinite(next) && next + 30_000 > Date.now();
  const state = fresh && ['reachable','unreachable'].includes(snapshot?.state) ? snapshot.state : 'unknown';
  this._connectionEl.hidden = !offline && (!snapshot || state === 'reachable');
  setText(this._connectionEl, this._t(offline ? 'connection.ha_lost' : 'connection.' + state));
  let time = '';
  if (Number.isFinite(checked)) {
    try { time = new Date(checked).toLocaleString(cardLanguage(this._hass)); }
    catch { time = new Date(checked).toISOString(); }
  }
  this._connectionEl.title = time ? this._t('connection.checked', { time }) : '';
};
// End shared localization helper.

// Text stays text, including device-supplied errors. Long recovery guidance expands.
function renderStatus(element, message, cls) {
  const className = 'status' + (cls ? ' ' + cls : '');
  if (typeof message === 'string' && element.textContent === message && element.className === className) return;
  element.replaceChildren();
  if (message instanceof Node) element.appendChild(message);
  else {
    const split = cls === 'err' && message.length > 100 ? message.indexOf('. ') : -1;
    if (split > 0) {
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = message.slice(0, split + 2);
      const recovery = document.createElement('div');
      recovery.textContent = message.slice(split + 2);
      details.append(summary, recovery);
      element.appendChild(details);
    } else element.textContent = message;
  }
  element.className = className;
}

const DOCUMENT_CARD_STYLES = `/* Shared document-card contract v1. Keep this base identical in both cards. */
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
      .options-button { margin-inline-start: auto; flex: none; width: 44px; padding: 8px; }
      .options { box-sizing: border-box; display: grid; gap: 12px; width: min(400px, calc(100vw - 32px)); max-height: 85vh; overflow: auto; padding: 20px; border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius, 12px); color: var(--primary-text-color); background: var(--card-background-color); }
      .options:not([open]) { display: none; }
      .options::backdrop { background: rgba(0, 0, 0, .45); }
      .options h2 { font-size: 20px; margin: 0 0 4px; }
      .option-field { display: grid; gap: 4px; min-width: 0; font-size: 14px; }
      .option-field select, .option-field input { box-sizing: border-box; width: 100%; min-width: 0; min-height: 44px; padding: 8px; font: inherit; color: var(--primary-text-color); background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 8px; }
      .options-help { color: var(--secondary-text-color); font-size: 12px; line-height: 18px; overflow-wrap: anywhere; }
      .warning { color: var(--warning-color, var(--primary-text-color)); font-size: 14px; line-height: 20px; overflow-wrap: anywhere; }
      /* End shared document-card base. */`;

// Shared document-card option helpers. Keep this small block identical in both cards.
function optionChoices(select, choices, value) {
  const signature = JSON.stringify(choices);
  if (select.dataset.choices !== signature) {
    select.replaceChildren(...choices.map(([key, label, disabled]) => {
      const option = document.createElement('option');
      option.value = String(key); option.textContent = label; option.disabled = !!disabled;
      return option;
    }));
    select.dataset.choices = signature;
  }
  select.value = String(value);
}
function addOptionField(panel, key, label, type = 'select') {
  const wrapper = document.createElement('label');
  wrapper.className = 'option-field';
  const caption = translatedText(label, {}, panel._hass); wrapper.append(caption);
  const input = document.createElement(type === 'select' ? 'select' : 'input');
  input.dataset.option = key;
  input.setAttribute('aria-describedby', 'options-help');
  if (type !== 'select') input.type = type;
  wrapper.append(input); panel.append(wrapper);
  return input;
}
// Let HA own Back navigation, including the Android app's dialog handling.
// The native panel stays in the card's shadow root to retain its theme/styles.
const OPTIONS_TAG = `${TAG}-options-dialog`;
if (!customElements.get(OPTIONS_TAG)) {
  customElements.define(OPTIONS_TAG, class extends HTMLElement {
    showDialog(params) {
      this._open = true;
      const card = params?.card;
      this._card = card;
      // Older HA history entries cannot serialize the live card reference.
      if (!card) { this.closeDialog(); return; }
      card._optionsDialog = this;
      // HA may finish loading the host after navigation or a quick dismissal.
      if (!card.isConnected || !card._optionsOpen) this.closeDialog();
    }
    closeDialog() {
      if (!this._open) return true;
      this._open = false;
      const card = this._card;
      this._card = null;
      if (card) {
        card._optionsDialog = null;
        card._toggleOptions(false, card.isConnected);
      }
      this.dispatchEvent(new CustomEvent('dialog-closed', {
        bubbles: true, composed: true, detail: { dialog: OPTIONS_TAG },
      }));
      return true;
    }
  });
}
C.prototype._toggleOptions = function (open, restoreFocus = true) {
  if (!this._optionsPanel || (open && (!this.isConnected || this._optionsOpen))) return;
  const wasOpen = this._optionsOpen;
  this._optionsOpen = open;
  this._optionsPanel.hidden = !open;
  this._optionsButton.setAttribute('aria-expanded', String(open));
  if (open) {
    this._refreshOptions();
    this._optionsButton.focus();
    this.dispatchEvent(new CustomEvent('show-dialog', {
      bubbles: true, composed: true,
      detail: {
        dialogTag: OPTIONS_TAG, dialogImport: () => Promise.resolve(),
        dialogParams: { card: this },
      },
    }));
    if (!this._optionsPanel.open) this._optionsPanel.showModal?.();
    this._optionsPanel.querySelector('h2')?.focus();
  } else {
    this._optionsPanel.close?.();
    this._optionsDialog?.closeDialog();
    if (wasOpen && restoreFocus && this.isConnected) this._optionsButton.focus();
  }
};
C.prototype._createOptionsPanel = function () {
  this._optionsButton = this.shadowRoot.querySelector('.options-button');
  this._optionsButton[Symbol.for('HA focus target')] = true;
  const panel = document.createElement('dialog');
  panel._hass = this._hass;
  panel.className = 'options'; panel.id = 'options'; panel.hidden = true;
  panel.setAttribute('aria-labelledby', 'options-heading');
  const heading = document.createElement('h2'); heading.id = 'options-heading'; heading.tabIndex = -1; heading.autofocus = true;
  heading.dataset.i18n = 'dialog.title'; heading.textContent = this._t('dialog.title');
  panel.append(heading); this.shadowRoot.append(panel);
  panel.addEventListener('cancel', event => { event.preventDefault(); this._toggleOptions(false); });
  // Native dismissals can close the panel without going through our buttons.
  panel.addEventListener('close', () => {
    if (!panel.open) this._toggleOptions(false);
  });
  this._optionsPanel = panel;
  this._optionsButton.addEventListener('click', () => this._toggleOptions(!this._optionsOpen));
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); this._toggleOptions(false); }
  });
  this._optionHelp = document.createElement('div');
  this._optionHelp.id = 'options-help'; this._optionHelp.className = 'options-help'; this._optionHelp.setAttribute('aria-live', 'polite');
  return panel;
};
C.prototype._finishOptionsPanel = function () {
  this._optionsPanel.append(this._optionHelp);
  const done = document.createElement('button'); done.type = 'button'; done.dataset.i18n = 'action.done'; done.textContent = this._t('action.done');
  done.addEventListener('click', () => this._toggleOptions(false));
  this._optionsPanel.append(done);
};
// Native hosts own identity/surface; the existing card still owns every workflow.
const DOCUMENT_FEATURE_STYLES = `
  :host { height: auto; min-width: 0; }
  .feature-body { display: flex; flex-direction: column; gap: 8px; min-width: 0; color: var(--primary-text-color); }
  .feature-body .status { min-height: 20px; }
  .feature-body .actions { display: flex; align-items: stretch; gap: 8px; }
  .feature-body .primary, .feature-body .cancel { flex: 1; width: auto; min-width: 0; }
  .feature-body button { border-radius: var(--feature-border-radius, 12px); min-height: max(44px, var(--feature-height, 42px)); }
  .feature-body .options-button { margin: 0; }
`;
C.prototype._configureFeatureView = function () {
  if (!this._featureMode) return;
  this._card.classList.add('feature-body');
  this.shadowRoot.querySelector('.header').hidden = true;
  this.shadowRoot.querySelector('.actions').append(this._optionsButton);
};

function supportsDocumentFeature(hass, context) {
  const id = context?.entity_id;
  if (typeof id !== 'string' || !id.startsWith('sensor.')) return false;
  const registered = hass?.entities?.[id];
  if (registered?.platform) return registered.platform === FEATURE_DOMAIN;
  // Older frontends can omit the registry; require the integration's enum shape.
  const attrs = hass?.states?.[id]?.attributes;
  return !!attrs && hasOwn(attrs, FEATURE_DOMAIN === 'escl_scan' ? 'scan_id' : 'job_id')
    && Array.isArray(attrs.options) && attrs.options.includes('processing-stopped')
    && attrs.options.includes(FEATURE_DOMAIN === 'escl_scan' ? 'awaiting-back-sides' : 'pending-held');
}

function preserveDocumentElements() {
  // A late scoped-registry polyfill can replace window.customElements after
  // this module has run. Native elements still exist, but HA's new registry
  // cannot find them. Keep the original constructors (and mounted workflows).
  const key = Symbol.for(TAG + '.element-registration');
  const tags = [TAG, FEATURE_TAG, TAG + '-editor', FEATURE_TAG + '-editor', OPTIONS_TAG];
  const definitions = tags.map(tag => [tag, customElements.get(tag)]);
  if (window[key]) {
    window[key].definitions = definitions;
    window[key].restore();
    return;
  }
  const state = { registry: customElements, definitions };
  state.restore = () => {
    const registry = window.customElements;
    if (registry === state.registry) return;
    for (const [tag, constructor] of state.definitions) {
      if (constructor && !registry.get(tag)) registry.define(tag, constructor);
    }
    state.registry = registry;
  };
  window[key] = state;
  // Capture script loads, including resources loaded after a slow first visit.
  // Normal loads cost only an identity check; no ongoing DOM scan or polling.
  document.addEventListener('load', state.restore, true);
  window.addEventListener('load', state.restore);
  window.addEventListener('pageshow', state.restore);
  window.addEventListener('location-changed', state.restore);
  customElements.whenDefined('home-assistant').then(state.restore);
}

function registerDocumentFeature() {
  const F = customElements.get(FEATURE_TAG);
  F.getStubConfig = () => ({ type: 'custom:' + FEATURE_TAG, duplex: false });
  const editorTag = FEATURE_TAG + '-editor';
  if (!customElements.get(editorTag)) {
    // Own tag and filtering also work when an older standalone editor loaded first.
    const Editor = customElements.get(TAG + '-editor');
    customElements.define(editorTag, class extends Editor {
      _render() {
        super._render();
        this._form.schema = this._form.schema.filter(field => !['title', 'entity'].includes(field.name));
      }
    });
  }
  F.getConfigElement = () => document.createElement(editorTag);
  F.prototype._t = C.prototype._t;
  F.prototype.setConfig = function (config) {
    if (!config || typeof config !== 'object') throw new Error(this._t('feature.config'));
    if (config.entity || config.title) throw new Error(this._t('feature.host_config'));
    C.prototype._validateConfig.call(this, config);
    this._config = { ...config };
    this._configRevision = (this._configRevision || 0) + 1;
    this._updateFeature();
  };
  for (const property of ['hass', 'context', 'stateObj', 'position']) {
    Object.defineProperty(F.prototype, property, {
      get() { return this['_' + property]; },
      set(value) {
        this['_' + property] = value;
        if (property === 'context') this._hasContext = true;
        this._updateFeature();
      },
      configurable: true,
    });
  }
  F.prototype._updateFeature = function () {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) {
      const root = this.attachShadow({ mode: 'open' });
      const style = document.createElement('style');
      style.textContent = ':host { display: block; min-width: 0; } .guidance { font-size: 14px; line-height: 20px; color: var(--secondary-text-color); overflow-wrap: anywhere; }';
      this._container = document.createElement('div');
      root.append(style, this._container);
      // Control gestures must not also invoke the host's tap/hold/double action.
      for (const type of ['click', 'dblclick', 'pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'keydown', 'keyup', 'action']) {
        root.addEventListener(type, event => event.stopPropagation());
      }
    }
    const context = this._hasContext ? this._context : this._stateObj;
    const entity = context?.entity_id;
    const supported = this._position !== 'inline' && supportsDocumentFeature(this._hass, context);
    if (!supported) {
      this._workflow?.remove();
      this._workflow = null;
      this._entity = null;
      this._container.className = 'guidance';
      this._container.textContent = this._t(this._position === 'inline' ? 'feature.bottom' : 'feature.target');
      return;
    }
    if (this._entity !== entity || !this._workflow) {
      this._workflow?.remove();
      this._workflow = document.createElement(TAG);
      this._workflow._featureMode = true;
      this._entity = entity;
      this._appliedRevision = null;
      this._container.className = '';
      this._container.replaceChildren();
    }
    if (this._appliedRevision !== this._configRevision) {
      this._workflow.setConfig({ ...this._config, type: 'custom:' + TAG, entity });
      this._appliedRevision = this._configRevision;
    }
    this._workflow.hass = this._hass;
    if (!this._workflow.parentNode) this._container.append(this._workflow);
  };
  window.customCardFeatures ||= [];
  if (!window.customCardFeatures.some(feature => feature.type === FEATURE_TAG)) {
    window.customCardFeatures.push({ type: FEATURE_TAG, name: localize('picker.name'), isSupported: supportsDocumentFeature, configurable: true });
  }
  preserveDocumentElements();
}
// END DOCUMENT CARD CORE v3


C.getStubConfig = function (hass) { return { title: localize('card.title', {}, hass) }; };

C.prototype._validateConfig = function (config) {
  if (config?.copies !== undefined && (!Number.isInteger(config.copies) || config.copies < 1 || config.copies > 99)) throw new Error(this._t('config.copies'));
  for (const key of ['duplex','duplex_in_options']) if (config?.[key] !== undefined && typeof config[key] !== 'boolean') throw new Error(this._t('config.boolean', { field: key }));
  if (config?.binding !== undefined && !['two-sided-long-edge','two-sided-short-edge'].includes(config.binding)) throw new Error(this._t('config.binding'));
};
C.prototype.setConfig = function (config) {
  this._validateConfig(config);
  const previousConfig = this._config;
  const previousEntity = this._config?.entity;
  this._config = Object.assign({ copies: 1, duplex: false, binding: 'two-sided-long-edge' }, config || {});
  this._settings ||= { copies: this._config.copies, binding: this._config.binding, media: '', media_source: '', color_mode: '', quality: '' };
  for (const key of ['copies','binding','duplex']) {
    if (previousConfig?.[key] !== this._config[key]) (this._pendingSettings ||= {})[key] = this._config[key];
  }
  if (previousEntity !== this._config.entity) this._pendingTargetReset = true;
  this._render();
  // _render is one-shot; apply config changes (card editor) directly.
  if (this._titleEl) this._titleEl.textContent = this._config.title || this._t('card.title');
  this._syncControls();
  this._onHass();
};

// hass is set every state update; keep the latest reference for the token.
Object.defineProperty(C.prototype, 'hass', {
  set(hass) { this._hass = hass; this._onHass(); this._syncControls(); this._refreshOptions(); },
  configurable: true,
});

C.prototype.getCardSize = function () { return 3; };
C.prototype.getGridOptions = function () { return { columns: 6, rows: 4, min_columns: 6, min_rows: 4 }; };

C.prototype._render = function () {
  if (this._rendered) return;
  const root = this.attachShadow({ mode: 'open' });
  const shell = this._featureMode ? 'div' : 'ha-card';
  root.innerHTML = `
    <style>
      ${DOCUMENT_CARD_STYLES}
      ${this._featureMode ? DOCUMENT_FEATURE_STYLES : ''}
      .toggle { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 44px; font-size: 14px; }
      .two-sided { appearance: none; position: relative; width: 36px; height: 22px; margin: 0; border-radius: 12px; background: var(--disabled-text-color); cursor: pointer; }
      .two-sided::before { content: ''; position: absolute; width: 16px; height: 16px; left: 3px; top: 3px; border-radius: 50%; background: var(--card-background-color); }
      .two-sided:checked { background: var(--primary-color); }
      .two-sided:checked::before { left: 17px; }
      .two-sided:disabled { opacity: .5; cursor: default; }
      .file-name { font-size: 14px; line-height: 20px; color: var(--secondary-text-color); overflow-wrap: anywhere; }
      .file-actions { display: flex; gap: 8px; margin-top: 8px; }
      .file-actions button { flex: 1; min-width: 0; padding: 8px 4px; }
    </style>
    <${shell} class="document-body">
      <div class="header"><ha-icon class="icon" icon="mdi:printer" aria-hidden="true"></ha-icon><div class="title"></div><button class="options-button" type="button" aria-expanded="false" aria-controls="options" data-i18n-label="dialog.title" title=""><ha-icon icon="mdi:tune" aria-hidden="true"></ha-icon></button></div>
      <div class="status" aria-live="polite" aria-atomic="true"></div>
      <div class="connection warning" aria-live="polite" hidden></div>
      <div class="controls">
        <label class="toggle"><span data-i18n="action.two_sided"></span><input class="two-sided" type="checkbox" role="switch" data-i18n-label="accessibility.two_sided"></label>
        <div class="file-name"></div>
        <div class="file-actions" hidden><button class="replace" type="button" data-i18n="action.replace"></button><button class="clear" type="button" data-i18n="action.clear"></button></div>
      </div>
      <div class="actions">
        <button class="primary" type="button"></button>
        <button class="cancel" type="button" data-i18n="action.cancel"></button>
      </div>
    </${shell}>
  `;
  this._card = root.querySelector('.document-body');
  this._titleEl = root.querySelector('.title');
  this._statusEl = root.querySelector('.status');
  this._connectionEl = root.querySelector('.connection');
  this._cancelEl = root.querySelector('.cancel');
  this._primaryEl = root.querySelector('.primary');
  this._fileNameEl = root.querySelector('.file-name');
  this._fileActionsEl = root.querySelector('.file-actions');
  this._titleEl.textContent = this._config.title || this._t('card.title');
  this._twoSidedEl = root.querySelector('.two-sided');
  this._twoSidedEl.addEventListener('change', () => {
    if (this._busy || this._activeJobId != null) { this._syncControls(); return; }
    this._duplex = this._twoSidedEl.checked; this._refreshOptions(); this._syncControls();
  });
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
  this._installOptions();
  this._configureFeatureView();
  this._rendered = true;
  this._setStatus('');
  this._syncControls();
};

C.prototype._syncControls = function () {
  if (!this._primaryEl) return;
  this._applyLanguage();
  this._syncConnection();
  const offline = this._hass?.connected === false;
  this._cancelEl.disabled = offline;
  const locked = !!this._busy || this._activeJobId != null;
  if (!locked && this._pendingTargetReset) {
    this._pendingTargetReset = false;
    this._selectedEntity = null; this._optionCapabilities = null; this._optionsRequest?.abort();
  }
  if (!locked && this._pendingSettings) {
    const { duplex, ...settings } = this._pendingSettings;
    Object.assign(this._settings, settings);
    if (duplex !== undefined) this._duplex = duplex;
    this._pendingSettings = null;
  }
  this._primaryEl.disabled = locked || offline;
  this._primaryEl.hidden = !!this._showCancel;
  this._primaryEl.textContent = this._busy ? this._t('action.submitting')
    : this._activeJobId != null ? this._t('action.printing') : this._stagedFile ? this._t('action.print') : this._t('action.choose_file');
  setText(this._fileNameEl, (this._activeJobId != null ? this._jobFilename : this._stagedFile?.name) || this._t('file.hint'));
  this._fileActionsEl.hidden = !this._stagedFile || locked;
  for (const button of this._fileActionsEl.querySelectorAll('button')) button.disabled = locked;
  this._syncOptions(locked || offline);
  if (!locked && this._stagedFile && this._settingsError) this._primaryEl.disabled = true;
};

function fileError(file, hass) {
  if (!file) return localize('error.no_file', {}, hass);
  if (file.size > 50 * 1024 * 1024) return localize('error.file_size', {}, hass);
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name) && !ACCEPTED_TYPES.has(file.type)) {
    return localize('error.file_type', {}, hass);
  }
  return null;
}

C.prototype._stageFile = function (file) {
  if (this._busy || this._activeJobId != null) return;
  const error = fileError(file, this._hass);
  if (error) { this._setStatus(error, 'err'); return; }
  this._stopProgress();
  this._stagedFile = file;
  this._jobFilename = null;
  this._warningEl.textContent = '';
  this._setMessage('status.ready');
  this._refreshOptions();
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
  if (this._busy && this._submissionSensorId) return this._submissionSensorId;
  if (this._activeJobId != null && this._activeSensorId) return this._activeSensorId;
  if (this._selectedEntity) return this._selectedEntity;
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
    throw new Error(this._t('error.printers'));
  }
  return null;
};

C.prototype._jobToken = function () {
  return JSON.stringify([this._activeSensorId, this._activeJobId, this._activeSubmittedAt, this._progressGeneration]);
};
C.prototype._cancelJob = async function () {
  if (this._activeJobId == null || this._hass?.connected === false) return;
  const token = this._jobToken();
  if (this._cancelPending?.token === token) return;
  const pending = { token };
  this._cancelPending = pending;
  const current = () => this.isConnected && this._jobToken() === token;
  const request = { job_id: this._activeJobId, entity_id: this._activeSensorId };
  if (this._activeSubmittedAt) request.submitted_at = this._activeSubmittedAt;
  try {
    const r = await this._authedFetch('/api/ipp_print/cancel', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
    });
    const body = r.ok ? '' : await r.text();
    if (!current()) return;
    if (!r.ok) this._setMessage('status.cancel_failed', { error: body.slice(0, 80) }, 'err');
    else this._setMessage('action.canceling');
  } catch (err) {
    if (current()) this._setMessage('status.cancel_failed', { error: err?.message || err }, 'err');
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
  const key = this._stagedFile ? 'status.ready' : 'status.choose';
  this._statusMessage = text ? null : { key, values: {}, cls };
  renderStatus(this._statusEl, text || this._t(key), cls);
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
  if (this._busy || this._activeJobId != null || this._hass?.connected === false) return;
  const error = fileError(file, this._hass);
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
  this._submissionSensorId = sensorId;
  const requestEpoch = this._requestEpoch || 0;
  const isCurrent = () => this.isConnected && requestEpoch === (this._requestEpoch || 0);
  this._card.classList.add('busy');
  this._setMessage('status.uploading');
  this._cleanupPicker?.();
  this._syncControls();

  const form = new FormData();
  if (sensorId) form.append('entity_id', sensorId);
  form.append('file', file, file.name);

  let definitelyRejected = true;
  try {
    await this._refreshOptions();
    if (!isCurrent() || this._hass?.connected === false) { definitelyRejected = true; throw new Error(this._t('error.changed')); }
    const options = this._optionCapabilities?.body?.request_options || [];
    if (this._settingsError) { definitelyRejected = true; throw new Error(this._settingsError); }
    if ((!options.includes('copies') && this._settings.copies !== 1)
        || ['media','media_source','color_mode','quality'].some(key => this._settings[key] && !options.includes(key))) {
      definitelyRejected = true;
      throw new Error(this._t('error.settings'));
    }
    if (this._duplex && !options.includes('sides')) { definitelyRejected = true; throw new Error(this._t('error.duplex')); }
    if (options.includes('copies')) form.append('copies', String(this._settings.copies));
    if (options.includes('sides')) form.append('sides', this._duplex ? this._settings.binding : 'one-sided');
    for (const key of ['media', 'media_source', 'color_mode', 'quality']) {
      if (this._settings[key] && options.includes(key)) form.append(key, String(this._settings[key]));
    }
    // Returns the printer-assigned job-id we then track via the job sensor.
    definitelyRejected = false;
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
      definitelyRejected = body?.job_may_exist === false
        || (resp.status >= 400 && resp.status < 500 && resp.status !== 408);
      const msg = [body?.message, body?.error].find(value => typeof value === 'string' && value.trim());
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    if (!Number.isInteger(body?.job_id) || body.job_id <= 0) {
      throw new Error(this._t('error.response'));
    }
    if (!isCurrent()) throw new Error(this._t('error.changed'));
    const name = typeof body.filename === 'string' && body.filename ? body.filename : file.name;
    this._stagedFile = null;
    this._jobFilename = name;
    this._activeJobId = body?.job_id ?? null;
    this._activeSensorId = sensorId;
    this._activeSubmittedAt = typeof body.submitted_at === 'string' ? body.submitted_at : null;
    this._awaitingSnapshot = true;
    this._setCancelVisible(true);
    this._setMessage('status.submitted', { name }, 'ok');
    this._warningEl.textContent = typeof body.warning === 'string' ? body.warning : '';
    this._lastJobSig = null;
  } catch (err) {
    if (!definitelyRejected) this._stagedFile = null;
    const guidance = definitelyRejected ? '' : this._msg('help.uncertain');
    if (this.isConnected) this._setMessage('status.submit_failed', { error: err?.message || err, guidance }, 'err');
  } finally {
    this._busy = false;
    this._submissionSensorId = null;
    this._card.classList.remove('busy');
    this._syncControls();
    this._onHass();
  }
};

// HA already pushes the selected sensor to every card. No extra socket
// subscription, connection listener or device poll belongs in the frontend.
const TERMINAL_STATES = new Set(['canceled', 'aborted', 'completed', 'unknown']);
const ACTIVE_STATES = new Set(['pending', 'pending-held', 'processing', 'processing-stopped']);

C.prototype._stopProgress = function () {
  this._progressGeneration = (this._progressGeneration || 0) + 1;
  clearTimeout(this._progressSafety);
  this._progressSafety = null;
};
C.prototype._disconnected = function () {
  this._toggleOptions(false, false);
  this._cleanupPicker?.();
  this._optionsRequest?.abort();
  this._requestEpoch = (this._requestEpoch || 0) + 1;
  this._lastJobSig = null;
  this._stopProgress();
};
C.prototype._connected = function () {
  this._lastJobSig = null;
  this._onHass();
};

C.prototype._renderJobState = function (state, attrs) {
  setText(this._warningEl, typeof attrs.warning === 'string' ? attrs.warning : '');
  const validCount = value => Number.isInteger(value) && value >= 0 ? value : null;
  const done = validCount(attrs.pages_done);
  if (state === 'processing') {
    // Some printers grow job-impressions while rendering (HP: 0 -> 2 -> 4).
    // A provisional total must not make an active job look finished at 2/2.
    const progress = done != null
      ? this._msg(attrs.progress_unit === 'sheets' ? 'status.sheet' : 'status.page', { count: done }) : '';
    this._setMessage('status.printing', { progress });
  } else if (state === 'pending' || state === 'pending-held') this._setMessage('status.queued');
  else if (state === 'processing-stopped') {
    this._setMessage('status.paused', { reason: attrs.state_reasons ? this._msg('status.reason', { reason: attrs.state_reasons }) : '' });
  } else if (state === 'completed') {
    // A requested total is not evidence of an actual completed page count.
    this._setMessage(done != null ? (attrs.progress_unit === 'sheets' ? 'status.complete_sheets' : 'status.complete') : 'status.complete_unknown', { count: done }, 'ok');
  } else if (state === 'canceled') this._setMessage('status.canceled', {}, 'err');
  else if (state === 'aborted') this._setMessage('status.failed', { reason: attrs.state_reasons ? this._msg('status.reason', { reason: attrs.state_reasons }) : '' }, 'err');
  else if (state === 'unknown') this._setMessage('status.unknown', {}, 'err');
};

C.prototype._onHass = function () {
  if (!this._rendered || !this.isConnected || !this._hass || this._busy || this._hass.connected === false) return;
  let entity;
  try { entity = this._sensorId(); } catch { return; }
  const st = this._hass.states?.[entity], attrs = st?.attributes || {};
  if (entity !== this._observedEntity) {
    this._observedEntity = entity;
    this._lastJobSig = null;
    this._dismissedJobKey = null;
    this._observedJobTime = null;
    this._observedStateTime = null;
    this._stopProgress();
    this._setStatus('');
    setText(this._warningEl, '');
  }
  // Ignore a delayed snapshot older than the one already shown for this device.
  const stateTime = Date.parse(st?.last_updated);
  const jobTime = Date.parse(attrs.submitted_at);
  if ((Number.isFinite(stateTime) && this._observedStateTime != null && stateTime < this._observedStateTime)
      || (Number.isFinite(jobTime) && this._observedJobTime != null && jobTime < this._observedJobTime)) return;
  if (Number.isFinite(stateTime)) this._observedStateTime = stateTime;
  if (Number.isFinite(jobTime)) this._observedJobTime = jobTime;
  const validId = Number.isInteger(attrs.job_id) && attrs.job_id > 0;
  const key = JSON.stringify([entity, attrs.job_id, attrs.submitted_at || null]);
  if (this._awaitingSnapshot && this._activeJobId != null && (attrs.job_id !== this._activeJobId
      || (this._activeSubmittedAt && attrs.submitted_at !== this._activeSubmittedAt))) {
    const newer = this._activeSubmittedAt && attrs.submitted_at > this._activeSubmittedAt;
    if (!newer && !['unknown','unavailable'].includes(st?.state)) {
      if (!this._progressSafety) this._progressSafety = setTimeout(() => {
        this._progressSafety = null;
        this._awaitingSnapshot = false;
        this._activeJobId = null;
        this._jobFilename = null;
        this._setMessage('status.no_updates', {}, 'err');
        this._setCancelVisible(false);
        this._lastJobSig = null;
        this._onHass();
      }, 90_000);
      return;
    }
  }
  const sig = JSON.stringify([key, st?.state, attrs.pages_done, attrs.pages_total, attrs.progress_unit, attrs.state_reasons, attrs.warning, attrs.filename]);
  if (sig === this._lastJobSig) return;
  this._lastJobSig = sig;
  const active = validId && ACTIVE_STATES.has(st?.state);
  const terminal = validId && TERMINAL_STATES.has(st?.state);
  if (active || terminal) {
    this._awaitingSnapshot = false;
    if (key !== this._jobKey) { this._stopProgress(); this._jobKey = key; }
    if (active) {
      clearTimeout(this._progressSafety);
      this._progressSafety = null;
      this._activeJobId = attrs.job_id;
      this._activeSensorId = entity;
      this._activeSubmittedAt = attrs.submitted_at || null;
      this._jobFilename = typeof attrs.filename === 'string' ? attrs.filename : null;
      this._renderJobState(st.state, attrs);
      this._setCancelVisible(true);
    } else {
      this._activeJobId = null;
      this._jobFilename = null;
      this._setCancelVisible(false);
      if (this._dismissedJobKey === key) return;
      this._renderJobState(st.state, attrs);
      if (!this._progressSafety) this._progressSafety = setTimeout(() => {
        this._progressSafety = null;
        this._dismissedJobKey = key;
        this._setStatus('');
      }, 10_000);
    }
  } else if (this._activeJobId != null) {
    this._stopProgress();
    this._awaitingSnapshot = false;
    this._activeJobId = null;
    this._jobFilename = null;
    this._setMessage('status.sensor_unavailable', {}, 'err');
    this._setCancelVisible(false);
  }
};

window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: localize('picker.name'),
    description: localize('picker.description'),
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



// Display labels only: the original advertised keywords remain option values.
function readableKeyword(value) {
  return String(value).replace(/[_-]+/g, ' ').replace(/\b[a-z]/g, letter => letter.toUpperCase());
}
function paperLabel(value, hass) {
  const raw = String(value);
  const match = /^([a-z]+)_([^_]+)_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(in|mm)$/.exec(raw.toLowerCase());
  if (!match) return readableKeyword(raw);
  const [, family, name, width, height, unit] = match;
  const names = {
    na_letter: localize('paper.letter', {}, hass), na_legal: localize('paper.legal', {}, hass), na_executive: localize('paper.executive', {}, hass),
    na_ledger: localize('paper.ledger', {}, hass), na_tabloid: localize('paper.tabloid', {}, hass), na_invoice: localize('paper.statement', {}, hass),
    na_foolscap: localize('paper.foolscap', {}, hass), na_oficio: localize('paper.oficio', {}, hass), na_monarch: localize('paper.monarch', {}, hass),
    'om_small-photo': localize('paper.photo', {}, hass), jpn_hagaki: localize('paper.hagaki', {}, hass),
    jpn_oufuku: localize('paper.reply', {}, hass), custom_min: localize('paper.min', {}, hass), custom_max: localize('paper.max', {}, hass),
  };
  let label = names[`${family}_${name}`];
  if (!label && family === 'na' && name.startsWith('number-')) label = localize('paper.envelope', { name: '#' + name.slice(7) }, hass);
  if (!label && family === 'na' && name.startsWith('index-')) label = localize('paper.index', {}, hass);
  if (!label && family === 'iso' && /^a\d+$/.test(name)) label = name.toUpperCase();
  if (!label && family === 'iso' && /^(c\d+|dl)$/.test(name)) label = localize('paper.envelope', { name: name.toUpperCase() }, hass);
  if (!label && ['prc', 'roc'].includes(family) && /^\d+k(?:-\d+x\d+)?$/.test(name)) {
    label = `${family.toUpperCase()} ${name.split('-')[0].toUpperCase()}`;
  }
  if (!label && ['iso', 'jis', 'jpn', 'prc', 'roc'].includes(family)) {
    // The family disambiguates names such as ISO B5 and JIS B5.
    label = `${family.toUpperCase()} ${readableKeyword(name)}`;
  }
  if (!label) label = readableKeyword(`${family}_${name}`);
  return localize('paper.dimensions', { name: label, width, height, unit }, hass);
}
function printOptionLabel(key, value, hass) {
  if (key === 'media') return paperLabel(value, hass);
  const labels = {
    media_source: { auto: localize('choice.automatic', {}, hass), manual: localize('choice.manual_feed', {}, hass), 'by-pass-tray': localize('choice.bypass', {}, hass), 'main': localize('choice.main_tray', {}, hass), 'alternate': localize('choice.alternate_tray', {}, hass) },
    color_mode: { auto: localize('choice.automatic', {}, hass), 'auto-monochrome': localize('choice.auto_monochrome', {}, hass), monochrome: localize('choice.monochrome', {}, hass), color: localize('field.color', {}, hass) },
    quality: { 3: localize('choice.draft', {}, hass), 4: localize('choice.normal', {}, hass), 5: localize('choice.best', {}, hass) },
  };
  const label = labels[key]?.[value];
  return typeof label === 'string' ? label : readableKeyword(value);
}

C.prototype._installOptions = function () {
  const panel = this._createOptionsPanel();
  this._optionFields = {
    entity_id: addOptionField(panel, 'entity_id', 'field.printer'),
    copies: addOptionField(panel, 'copies', 'field.copies', 'number'),
    binding: addOptionField(panel, 'binding', 'field.binding'),
    media: addOptionField(panel, 'media', 'field.paper'),
    media_source: addOptionField(panel, 'media_source', 'field.tray'),
    color_mode: addOptionField(panel, 'color_mode', 'field.color'),
    quality: addOptionField(panel, 'quality', 'field.quality'),
  };
  for (const [key, field] of Object.entries(this._optionFields)) {
    field.addEventListener('change', () => {
      if (field.disabled || this._busy || this._activeJobId != null) return;
      if (key === 'entity_id') {
        this._selectedEntity = field.value || null;
        this._optionCapabilities = null; this._optionsRequest?.abort();
        this._settings.media = this._settings.media_source = this._settings.color_mode = this._settings.quality = '';
        this._refreshOptions();
      } else this._settings[key] = key === 'copies' ? Number(field.value) : field.value;
      this._syncControls();
    });
  }
  this._warningEl = document.createElement('div'); this._warningEl.className = 'warning';
  this._warningEl.setAttribute('aria-live', 'polite');
  this.shadowRoot.querySelector('.status').after(this._warningEl);
  this._finishOptionsPanel();
};
C.prototype._refreshOptions = function () {
  if (this._hass?.connected === false) return Promise.resolve();
  let entity;
  try { entity = this._sensorId(); } catch { this._syncControls(); return Promise.resolve(); }
  if (!entity || !this.isConnected) return Promise.resolve();
  const file = this._stagedFile;
  const fmt = ACCEPTED_TYPES.has(file?.type) ? file.type : /\.pdf$/i.test(file?.name || '') ? 'application/pdf'
    : /\.png$/i.test(file?.name || '') ? 'image/png' : file ? 'image/jpeg' : null;
  const key = `${entity}|${fmt || ''}`;
  if (this._optionsRequest?.key === key && !this._optionsRequest.signal.aborted) return this._optionsPromise;
  if (this._optionCapabilities?.key === key && this._optionCapabilities.expires > Date.now()) return Promise.resolve();
  this._optionsRequest?.abort();
  const request = new AbortController(); request.key = key;
  this._optionsRequest = request;
  const caps = { key, expires: Date.now() + 300_000, body: null };
  this._optionCapabilities = caps;
  this._optionsPromise = (async () => {
    const timeout = setTimeout(() => request.abort(), 20_000);
    try {
      const base = '/api/ipp_print/capabilities?entity_id=' + encodeURIComponent(entity);
      let response = await this._authedFetch(base + (fmt ? '&document_format=' + encodeURIComponent(fmt) : ''), { signal: request.signal });
      if (fmt && response.status === 400 && !request.signal.aborted) response = await this._authedFetch(base, { signal: request.signal });
      if (!response.ok) return;
      const body = await response.json();
      if (request.signal.aborted || this._optionCapabilities !== caps || body?.schema_version !== 1
          || body.domain !== 'ipp_print' || body.entity_id !== entity || body.status !== 'fresh') return;
      caps.body = body;
      caps.expires = Date.now() + Math.max(1, Math.min(900, Number(body.refresh_after_seconds) || 300)) * 1000;
    } catch { /* Existing default printing remains available without new capability metadata. */ }
    finally {
      clearTimeout(timeout);
      if (this._optionsRequest === request) this._optionsRequest = null;
      this._syncControls();
    }
  })();
  return this._optionsPromise;
};
C.prototype._syncOptions = function (locked) {
  if (!this._optionFields) return;
  const body = this._optionCapabilities?.expires > Date.now() ? this._optionCapabilities.body : null;
  const supported = body?.supported || {};
  const options = Array.isArray(body?.request_options) ? body.request_options : [];
  const fields = this._optionFields, settings = this._settings;
  if (locked) {
    this._twoSidedEl.disabled = true;
    for (const field of Object.values(fields)) field.disabled = true;
    return;
  }
  this._settingsError = '';
  const toggle = this._twoSidedEl.closest('label');
  const parent = this._config.duplex_in_options ? this._optionsPanel : this.shadowRoot.querySelector('.controls');
  if (toggle.parentElement !== parent) parent.prepend(toggle);
  this._twoSidedEl.checked = !!this._duplex;
  this._twoSidedEl.disabled = locked || (!this._duplex && (!options.includes('sides')
    || (Array.isArray(supported.sides) && !supported.sides.some(x => typeof x === 'string' && x.startsWith('two-sided')))));
  const hass = this._getHass();
  const printers = Object.values(hass?.entities || {}).filter(e => e.platform === 'ipp_print' && e.entity_id?.startsWith('sensor.')).slice(0, 128);
  let selected = ''; try { selected = this._sensorId() || ''; } catch {}
  optionChoices(fields.entity_id, [['', this._t('choice.printer')], ...printers.map(e => [e.entity_id, hass?.states?.[e.entity_id]?.attributes?.friendly_name || e.entity_id])], selected);
  fields.entity_id.closest('label').hidden = this._featureMode || printers.length < 2;
  fields.entity_id.disabled = this._featureMode || locked;
  fields.copies.min = '1'; fields.copies.max = String(Math.min(99, supported.copies_max || 99));
  if (this.shadowRoot.activeElement !== fields.copies) fields.copies.value = settings.copies;
  fields.copies.disabled = locked || (!options.includes('copies') && settings.copies === 1);
  const sides = Array.isArray(supported.sides) ? supported.sides : ['two-sided-long-edge','two-sided-short-edge'];
  optionChoices(fields.binding, [['two-sided-long-edge', this._t('choice.long_edge'), !sides.includes('two-sided-long-edge')], ['two-sided-short-edge', this._t('choice.short_edge'), !sides.includes('two-sided-short-edge')]], settings.binding);
  fields.binding.disabled = locked || !this._duplex || !options.includes('sides');
  const lists = { media: supported.media, media_source: supported.media_sources, color_mode: supported.color_modes, quality: supported.qualities };
  for (const [key, list] of Object.entries(lists)) {
    const choices = Array.isArray(list) ? list.filter(x => typeof x === 'string' || Number.isInteger(x)).slice(0,128) : [];
    if (settings[key] && !choices.some(x => String(x) === String(settings[key]))) {
      choices.push(settings[key]);
      this._settingsError = this._t('error.setting_unavailable');
    }
    optionChoices(fields[key], [['',this._t('choice.device_default')], ...choices.map(value => [value, printOptionLabel(key, value, this._hass)])], settings[key]);
    fields[key].disabled = locked || (!settings[key] && (!options.includes(key) || !choices.length));
  }
  if (this._duplex && !sides.includes(settings.binding)) this._settingsError = this._t('error.binding');
  if (!Number.isInteger(settings.copies) || settings.copies < 1 || settings.copies > Number(fields.copies.max)) this._settingsError = this._t('error.copies_range', { max: fields.copies.max });
  setText(this._optionHelp, this._settingsError || (!body ? this._t('help.unavailable')
    : !this._stagedFile && this._activeJobId == null ? this._t('help.document')
    : this._duplex && !sides.includes(settings.binding) ? this._t('help.binding')
    : this._t('help.next_job', { loaded: Array.isArray(supported.media_ready) && supported.media_ready.length ? this._t('help.loaded', { paper: supported.media_ready.map(value => paperLabel(value, this._hass)).join(', ') }) : '' })));
};
C.getConfigElement = function () { return document.createElement(TAG + '-editor'); };
if (!customElements.get(TAG + '-editor')) {
  customElements.define(TAG + '-editor', class extends HTMLElement {
    setConfig(config) { this._config = config || {}; this._render(); }
    set hass(hass) { this._hass = hass; if (this._form) this._render(); }
    _render() {
      if (!this._form) {
        this._form = document.createElement('ha-form');
        this._form.addEventListener('value-changed', event => {
          event.stopPropagation();
          const config = { ...this._config, ...event.detail.value };
          if (!config.entity) delete config.entity;
          if (!config.title) delete config.title;
          if (config.copies == null || config.copies === '') delete config.copies;

          this._config = config;
          this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
        });
        this.append(this._form);
      }
      const language = cardLanguage(this._hass);
      if (language !== this._language) {
        this._language = language;
        const t = key => localize(key, {}, this._hass);
        const choices = entries => entries.map(([value, key]) => ({ value, label: t(key) }));
        this._form.schema = [
          { name: 'title', selector: { text: {} } },
          { name: 'entity', selector: { entity: { domain: 'sensor', integration: 'ipp_print' } } },
          { name: 'copies', selector: { number: { min: 1, max: 99, mode: 'box' } } },
          { name: 'duplex', selector: { boolean: {} } },
          { name: 'binding', selector: { select: { options: choices([['two-sided-long-edge','choice.long_edge'],['two-sided-short-edge','choice.short_edge']]) } } },
          { name: 'duplex_in_options', selector: { boolean: {} } },
        ];
        const labels = {"title": "editor.title", "entity": "editor.entity", "copies": "editor.copies", "duplex": "editor.duplex", "binding": "editor.binding", "duplex_in_options": "editor.duplex_options"};
        this._form.computeLabel = field => t(labels[field.name]);
        this._form.computeHelper = field => {
          const key = 'editor.help.' + field.name;
          const help = t(key); return help === key ? '' : help;
        };
      }
      this._form.hass = this._hass;
      this._form.data = { ...{ copies: 1, duplex: false, binding: 'two-sided-long-edge', duplex_in_options: false }, ...this._config };
    }
  });
}

C.prototype._connectionSnapshot = function () {
  let entity; try { entity = this._sensorId(); } catch { return null; }
  return this._hass?.states?.[entity]?.attributes?.device_connection;
};

registerDocumentFeature();
