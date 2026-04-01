/**
 * SlotSentry Panel — HA sidebar frontend
 * Custom element: slotsentry-panel
 * Version: 2026.4.0a1
 *
 * Single-file LitElement panel served via panel_custom at:
 *   /local/slotsentry/slotsentry-panel.js
 *
 * WebSocket commands used:
 *   slotsentry/get_slots   — load all slots
 *   slotsentry/set_slot    — save a slot
 *   slotsentry/delete_slot — clear a slot
 *   slotsentry/push_all    — push all dirty slots to all locks
 *   slotsentry/push_lock   — push all dirty slots to one lock
 *   slotsentry/get_status  — per-lock sync summary
 */

// ---------------------------------------------------------------------------
// LitElement shim — use HA's bundled version if available, otherwise fall
// back to a minimal reactive-property / render loop so the panel works even
// during HA's JS bundle loading phase.
// ---------------------------------------------------------------------------

const { LitElement, html, css } =
  window.LitElement
    ? window
    : (() => {
        // Minimal shim — good enough while the real bundle loads.
        class LitElement extends HTMLElement {
          static get properties() { return {}; }
          static get styles() { return []; }
          constructor() {
            super();
            this.attachShadow({ mode: "open" });
            this._props = {};
          }
          set hass(v) { this._props.hass = v; this._requestRender(); }
          get hass() { return this._props.hass; }
          set panel(v) { this._props.panel = v; this._requestRender(); }
          get panel() { return this._props.panel; }
          connectedCallback() { this._requestRender(); }
          _requestRender() {
            if (this._renderScheduled) return;
            this._renderScheduled = true;
            Promise.resolve().then(() => {
              this._renderScheduled = false;
              this._doRender();
            });
          }
          _doRender() {
            const tmpl = this.render();
            if (!tmpl) return;
            this.shadowRoot.innerHTML = "";
            const styles = this.constructor.styles || [];
            const styleEl = document.createElement("style");
            styleEl.textContent = (Array.isArray(styles) ? styles : [styles])
              .map(s => (s && s.cssText) ? s.cssText : String(s))
              .join("\n");
            this.shadowRoot.appendChild(styleEl);
            // Minimal html tag template support
            const div = document.createElement("div");
            div.innerHTML = tmpl.strings
              ? tmpl.strings.reduce((acc, s, i) => acc + s + (tmpl.values[i] != null ? tmpl.values[i] : ""), "")
              : String(tmpl);
            while (div.firstChild) this.shadowRoot.appendChild(div.firstChild);
          }
          render() { return null; }
          requestUpdate() { this._requestRender(); }
        }
        const html = (strings, ...values) => ({ strings, values });
        const css = (strings, ...values) => ({
          cssText: strings.reduce((acc, s, i) => acc + s + (values[i] != null ? values[i] : ""), "")
        });
        return { LitElement, html, css };
      })();

// ---------------------------------------------------------------------------
// SlotSentryPanel
// ---------------------------------------------------------------------------

class SlotSentryPanel extends LitElement {

  static get properties() {
    return {
      hass:            { type: Object },
      panel:           { type: Object },
      _entryId:        { type: String,  state: true },
      _slots:          { type: Array,   state: true },
      _status:         { type: Object,  state: true },
      _loading:        { type: Boolean, state: true },
      _pushing:        { type: Boolean, state: true },
      _pushProgress:   { type: String,  state: true },
      _toasts:         { type: Array,   state: true },
      _revealMap:      { type: Object,  state: true },
      _savingSlots:    { type: Object,  state: true },
      _deletingSlots:  { type: Object,  state: true },
      _pushingLocks:   { type: Object,  state: true },
      _error:          { type: String,  state: true },
      _editValues:     { type: Object,  state: true },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
        height: 100%;
        overflow-y: auto;
        background: var(--primary-background-color, #f0f0f0);
        color: var(--primary-text-color, #212121);
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        font-size: 14px;
      }

      /* ------------------------------------------------------------------ */
      /* Header                                                              */
      /* ------------------------------------------------------------------ */

      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px;
        background: var(--primary-color, #03a9f4);
        color: #fff;
        position: sticky;
        top: 0;
        z-index: 100;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
      }

      .header h1 {
        margin: 0;
        font-size: 20px;
        font-weight: 500;
        letter-spacing: 0.01em;
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .header-icon {
        width: 28px;
        height: 28px;
        fill: #fff;
      }

      .header-actions {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .status-badge {
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        background: rgba(255,255,255,0.2);
        color: #fff;
      }

      .status-badge.synced    { background: rgba(76,175,80,0.85); }
      .status-badge.out_of_sync { background: rgba(255,152,0,0.85); }
      .status-badge.error     { background: rgba(244,67,54,0.85); }
      .status-badge.pushing   { background: rgba(33,150,243,0.85); }

      /* ------------------------------------------------------------------ */
      /* Buttons                                                             */
      /* ------------------------------------------------------------------ */

      .btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 7px 14px;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
        transition: opacity 0.15s, transform 0.1s;
        outline: none;
      }
      .btn:active { transform: scale(0.97); }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

      .btn-primary {
        background: #fff;
        color: var(--primary-color, #03a9f4);
      }
      .btn-primary:hover:not(:disabled) { background: rgba(255,255,255,0.85); }

      .btn-save {
        background: var(--primary-color, #03a9f4);
        color: #fff;
        padding: 5px 12px;
        font-size: 12px;
      }
      .btn-save:hover:not(:disabled) { opacity: 0.85; }

      .btn-delete {
        background: transparent;
        color: var(--error-color, #f44336);
        border: 1px solid var(--error-color, #f44336);
        padding: 5px 10px;
        font-size: 12px;
      }
      .btn-delete:hover:not(:disabled) {
        background: var(--error-color, #f44336);
        color: #fff;
      }

      .btn-push-lock {
        background: transparent;
        color: var(--primary-color, #03a9f4);
        border: 1px solid var(--primary-color, #03a9f4);
        padding: 5px 10px;
        font-size: 12px;
      }
      .btn-push-lock:hover:not(:disabled) {
        background: var(--primary-color, #03a9f4);
        color: #fff;
      }

      .btn-icon {
        background: transparent;
        color: inherit;
        padding: 4px;
        border-radius: 4px;
        opacity: 0.7;
      }
      .btn-icon:hover { opacity: 1; background: rgba(0,0,0,0.06); }
      .btn-icon svg { display: block; }

      /* ------------------------------------------------------------------ */
      /* Main content                                                        */
      /* ------------------------------------------------------------------ */

      .content {
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px 16px 40px;
      }

      /* ------------------------------------------------------------------ */
      /* Loading / error states                                              */
      /* ------------------------------------------------------------------ */

      .loading-container, .error-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 60px 20px;
        gap: 16px;
        color: var(--secondary-text-color, #727272);
      }

      .spinner {
        width: 40px;
        height: 40px;
        border: 3px solid var(--divider-color, #e0e0e0);
        border-top-color: var(--primary-color, #03a9f4);
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
      }
      @keyframes spin { to { transform: rotate(360deg); } }

      .error-container {
        color: var(--error-color, #f44336);
      }

      /* ------------------------------------------------------------------ */
      /* Push progress bar                                                   */
      /* ------------------------------------------------------------------ */

      .push-progress-bar {
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 13px;
        color: var(--primary-color, #03a9f4);
      }

      .push-progress-bar .spinner {
        width: 20px;
        height: 20px;
        border-width: 2px;
        flex-shrink: 0;
      }

      /* ------------------------------------------------------------------ */
      /* Slot table                                                          */
      /* ------------------------------------------------------------------ */

      .section-title {
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--secondary-text-color, #727272);
        margin: 0 0 10px;
        padding: 0;
      }

      .slot-card {
        background: var(--card-background-color, #fff);
        border-radius: 10px;
        border: 1px solid var(--divider-color, #e0e0e0);
        overflow: hidden;
        margin-bottom: 20px;
      }

      .slot-table-wrap {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }

      table {
        width: 100%;
        border-collapse: collapse;
        min-width: 640px;
      }

      thead tr {
        background: var(--secondary-background-color, #fafafa);
      }

      th {
        padding: 10px 12px;
        text-align: left;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--secondary-text-color, #727272);
        border-bottom: 2px solid var(--divider-color, #e0e0e0);
        white-space: nowrap;
      }

      tbody tr {
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        transition: background 0.1s;
      }
      tbody tr:last-child { border-bottom: none; }
      tbody tr:hover { background: var(--secondary-background-color, #fafafa); }
      tbody tr.slot-dirty { background: rgba(255,152,0,0.05); }

      td {
        padding: 8px 12px;
        vertical-align: middle;
      }

      .slot-num {
        font-weight: 700;
        color: var(--secondary-text-color, #727272);
        font-size: 13px;
        min-width: 32px;
        text-align: center;
      }

      .slot-input {
        width: 100%;
        padding: 6px 8px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 5px;
        background: var(--primary-background-color, #f0f0f0);
        color: var(--primary-text-color, #212121);
        font-size: 13px;
        font-family: inherit;
        box-sizing: border-box;
        transition: border-color 0.15s, box-shadow 0.15s;
        min-width: 80px;
      }
      .slot-input:focus {
        outline: none;
        border-color: var(--primary-color, #03a9f4);
        box-shadow: 0 0 0 2px rgba(3,169,244,0.15);
      }

      .code-cell {
        position: relative;
        display: flex;
        align-items: center;
        gap: 4px;
        min-width: 120px;
      }
      .code-cell .slot-input { flex: 1; min-width: 0; padding-right: 30px; }

      .reveal-btn {
        position: absolute;
        right: 4px;
        background: transparent;
        border: none;
        cursor: pointer;
        padding: 2px;
        color: var(--secondary-text-color, #727272);
        display: flex;
        align-items: center;
        border-radius: 3px;
        transition: color 0.15s;
      }
      .reveal-btn:hover { color: var(--primary-color, #03a9f4); }
      .reveal-btn svg { display: block; }

      .enabled-toggle {
        width: 18px;
        height: 18px;
        cursor: pointer;
        accent-color: var(--primary-color, #03a9f4);
      }

      .actions-cell {
        display: flex;
        gap: 6px;
        align-items: center;
        white-space: nowrap;
      }

      .empty-slot td {
        color: var(--secondary-text-color, #727272);
        font-style: italic;
      }

      /* ------------------------------------------------------------------ */
      /* Status section                                                      */
      /* ------------------------------------------------------------------ */

      .status-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 12px;
        margin-top: 4px;
      }

      .lock-card {
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 10px;
        padding: 14px 16px;
        transition: border-color 0.2s;
      }
      .lock-card.synced     { border-left: 4px solid #4caf50; }
      .lock-card.out_of_sync { border-left: 4px solid #ff9800; }
      .lock-card.uncertain  { border-left: 4px solid #9e9e9e; }
      .lock-card.error      { border-left: 4px solid #f44336; }

      .lock-name {
        font-weight: 600;
        font-size: 14px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .lock-state-pill {
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 10px;
        text-transform: uppercase;
      }
      .lock-state-pill.synced      { background: #e8f5e9; color: #388e3c; }
      .lock-state-pill.out_of_sync { background: #fff3e0; color: #f57c00; }
      .lock-state-pill.uncertain   { background: #f5f5f5; color: #757575; }
      .lock-state-pill.error       { background: #ffebee; color: #c62828; }

      .lock-counts {
        display: flex;
        gap: 14px;
        font-size: 12px;
        color: var(--secondary-text-color, #727272);
        margin-top: 4px;
      }

      .lock-count-item {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .lock-count-item .dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
      }
      .dot-synced   { background: #4caf50; }
      .dot-failed   { background: #f44336; }
      .dot-uncertain { background: #9e9e9e; }
      .dot-dirty    { background: #ff9800; }

      .dirty-slots {
        margin-top: 8px;
        font-size: 11px;
        color: var(--secondary-text-color, #727272);
      }

      .lock-actions {
        margin-top: 10px;
        display: flex;
        justify-content: flex-end;
      }

      .no-locks {
        color: var(--secondary-text-color, #727272);
        font-style: italic;
        font-size: 13px;
        padding: 8px 0;
      }

      /* ------------------------------------------------------------------ */
      /* Toast notifications                                                 */
      /* ------------------------------------------------------------------ */

      .toast-container {
        position: fixed;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9999;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
        pointer-events: none;
      }

      .toast {
        pointer-events: all;
        padding: 10px 20px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        color: #fff;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        animation: toast-in 0.2s ease, toast-out 0.3s ease 3.7s forwards;
        max-width: 400px;
        text-align: center;
      }
      @keyframes toast-in  { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
      @keyframes toast-out { from { opacity: 1; } to { opacity: 0; transform: translateY(8px); } }

      .toast.success { background: #43a047; }
      .toast.error   { background: #e53935; }
      .toast.info    { background: #1e88e5; }

      /* ------------------------------------------------------------------ */
      /* Responsive                                                          */
      /* ------------------------------------------------------------------ */

      @media (max-width: 600px) {
        .header { padding: 12px 14px; }
        .header h1 { font-size: 17px; }
        .content { padding: 12px 8px 32px; }
        .status-grid { grid-template-columns: 1fr; }
      }
    `;
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  constructor() {
    super();
    this._entryId      = null;
    this._slots        = [];
    this._status       = {};
    this._loading      = true;
    this._pushing      = false;
    this._pushProgress = "";
    this._toasts       = [];
    this._revealMap    = {};   // key: "long|short-<slotNum>" → bool
    this._savingSlots  = {};   // slotNum → bool
    this._deletingSlots = {};  // slotNum → bool
    this._pushingLocks = {};   // lockEntity → bool
    this._error        = null;
    this._editValues   = {};   // slotNum → { label, long_code, short_code, enabled }
    this._pushPollId   = null;
    this._pushPollStart = 0;
  }

  connectedCallback() {
    super.connectedCallback && super.connectedCallback();
    // Defer init until hass is available
    if (this.hass) {
      this._init();
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback && super.disconnectedCallback();
    this._stopPushPoll();
  }

  // When hass is set (first time or updated), kick init if not done yet.
  updated(changedProps) {
    if (changedProps && changedProps.has("hass") && this.hass && !this._entryId && !this._loading === false) {
      // _loading starts true — only init once
      if (this._initStarted) return;
      this._initStarted = true;
      this._init();
    }
  }

  // -------------------------------------------------------------------------
  // Initialisation
  // -------------------------------------------------------------------------

  async _init() {
    this._initStarted = true;
    this._loading = true;
    this._error = null;
    this.requestUpdate();

    try {
      await this._discoverEntryId();
    } catch (err) {
      this._error = `Failed to discover config entry: ${err.message || err}`;
      this._loading = false;
      this.requestUpdate();
      return;
    }

    if (!this._entryId) {
      this._error = "No SlotSentry config entry found. Please set up the integration first.";
      this._loading = false;
      this.requestUpdate();
      return;
    }

    await this._refresh();
    this._loading = false;
    this.requestUpdate();
  }

  async _discoverEntryId() {
    if (this.panel && this.panel.config && this.panel.config.entry_id) {
      this._entryId = this.panel.config.entry_id;
      return;
    }
    // Fallback: discover via config_entries/get
    const entries = await this.hass.callWS({ type: "config_entries/get", domain: "slotsentry" });
    if (entries && entries.length > 0) {
      this._entryId = entries[0].entry_id;
    }
  }

  async _refresh() {
    await Promise.all([this._loadSlots(), this._loadStatus()]);
  }

  async _loadSlots() {
    try {
      const result = await this.hass.callWS({
        type: "slotsentry/get_slots",
        entry_id: this._entryId,
      });
      this._slots = result.slots || [];
      // Seed edit values for new slots (don't overwrite existing edits)
      const next = { ...this._editValues };
      for (const slot of this._slots) {
        if (!next[slot.slot_number]) {
          next[slot.slot_number] = {
            label:      slot.label      || "",
            long_code:  slot.long_code  || "",
            short_code: slot.short_code || "",
            enabled:    slot.enabled    ?? true,
          };
        }
      }
      this._editValues = next;
      this.requestUpdate();
    } catch (err) {
      this._toast(`Failed to load slots: ${err.message || err}`, "error");
    }
  }

  async _loadStatus() {
    try {
      const result = await this.hass.callWS({
        type: "slotsentry/get_status",
        entry_id: this._entryId,
      });
      this._status = result.status || {};
      this.requestUpdate();
    } catch (err) {
      // Status is non-critical; don't show a blocking error
      this._status = {};
      this.requestUpdate();
    }
  }

  // -------------------------------------------------------------------------
  // Slot actions
  // -------------------------------------------------------------------------

  _onFieldInput(slotNumber, field, value) {
    const cur = this._editValues[slotNumber] || {};
    this._editValues = {
      ...this._editValues,
      [slotNumber]: { ...cur, [field]: value },
    };
    this.requestUpdate();
  }

  _onEnabledChange(slotNumber, checked) {
    const cur = this._editValues[slotNumber] || {};
    this._editValues = {
      ...this._editValues,
      [slotNumber]: { ...cur, enabled: checked },
    };
    this.requestUpdate();
  }

  async _saveSlot(slotNumber) {
    const vals = this._editValues[slotNumber];
    if (!vals) return;

    this._savingSlots = { ...this._savingSlots, [slotNumber]: true };
    this.requestUpdate();

    try {
      await this.hass.callWS({
        type:        "slotsentry/set_slot",
        entry_id:    this._entryId,
        slot_number: slotNumber,
        label:       vals.label || "",
        long_code:   vals.long_code || "",
        short_code:  vals.short_code || "",
        enabled:     !!vals.enabled,
      });
      this._toast(`Slot ${slotNumber} saved.`, "success");
      await this._refresh();
    } catch (err) {
      this._toast(`Save failed: ${err.message || err}`, "error");
    } finally {
      const s = { ...this._savingSlots };
      delete s[slotNumber];
      this._savingSlots = s;
      this.requestUpdate();
    }
  }

  async _deleteSlot(slotNumber) {
    const confirmed = window.confirm(
      `Clear slot ${slotNumber}? This will remove the label and codes and mark the slot for removal on the lock.`
    );
    if (!confirmed) return;

    this._deletingSlots = { ...this._deletingSlots, [slotNumber]: true };
    this.requestUpdate();

    try {
      await this.hass.callWS({
        type:        "slotsentry/delete_slot",
        entry_id:    this._entryId,
        slot_number: slotNumber,
      });
      this._toast(`Slot ${slotNumber} cleared.`, "success");
      // Remove cached edit values so they reload fresh
      const ev = { ...this._editValues };
      delete ev[slotNumber];
      this._editValues = ev;
      await this._refresh();
    } catch (err) {
      this._toast(`Delete failed: ${err.message || err}`, "error");
    } finally {
      const s = { ...this._deletingSlots };
      delete s[slotNumber];
      this._deletingSlots = s;
      this.requestUpdate();
    }
  }

  // -------------------------------------------------------------------------
  // Push actions
  // -------------------------------------------------------------------------

  async _pushAll() {
    if (this._pushing) return;
    this._pushing = true;
    this._pushProgress = "Initiating push to all locks…";
    this.requestUpdate();

    try {
      await this.hass.callWS({
        type:     "slotsentry/push_all",
        entry_id: this._entryId,
      });
      this._toast("Push initiated for all locks.", "info");
      this._startPushPoll();
    } catch (err) {
      this._toast(`Push failed: ${err.message || err}`, "error");
      this._pushing = false;
      this._pushProgress = "";
      this.requestUpdate();
    }
  }

  async _pushLock(lockEntity) {
    if (this._pushingLocks[lockEntity]) return;
    this._pushingLocks = { ...this._pushingLocks, [lockEntity]: true };
    this.requestUpdate();

    try {
      await this.hass.callWS({
        type:        "slotsentry/push_lock",
        entry_id:    this._entryId,
        lock_entity: lockEntity,
      });
      this._toast(`Push initiated for ${this._lockDisplayName(lockEntity)}.`, "info");
      // Brief poll for this lock
      this._startPushPoll();
    } catch (err) {
      this._toast(`Push failed for ${this._lockDisplayName(lockEntity)}: ${err.message || err}`, "error");
    } finally {
      const s = { ...this._pushingLocks };
      delete s[lockEntity];
      this._pushingLocks = s;
      this.requestUpdate();
    }
  }

  _startPushPoll() {
    this._stopPushPoll();
    this._pushPollStart = Date.now();
    this._pushProgress = "Syncing…";
    this._pushing = true;
    this.requestUpdate();

    this._pushPollId = setInterval(async () => {
      await this._loadStatus();
      const elapsed = Date.now() - this._pushPollStart;
      const allSynced = this._allLocksSynced();

      if (allSynced) {
        this._stopPushPoll();
        this._pushing = false;
        this._pushProgress = "";
        this._toast("All locks synced successfully.", "success");
        this.requestUpdate();
        return;
      }

      if (elapsed >= 30000) {
        this._stopPushPoll();
        this._pushing = false;
        this._pushProgress = "";
        this._toast("Push timed out. Check lock status below.", "error");
        this.requestUpdate();
        return;
      }

      const syncedLocks = Object.values(this._status).filter(s => s.state === "synced").length;
      const totalLocks  = Object.keys(this._status).length;
      this._pushProgress = `Syncing… ${syncedLocks}/${totalLocks} locks done (${Math.round(elapsed / 1000)}s)`;
      this.requestUpdate();
    }, 2000);
  }

  _stopPushPoll() {
    if (this._pushPollId) {
      clearInterval(this._pushPollId);
      this._pushPollId = null;
    }
  }

  _allLocksSynced() {
    const entries = Object.values(this._status);
    if (entries.length === 0) return false;
    return entries.every(s => s.state === "synced");
  }

  // -------------------------------------------------------------------------
  // Reveal toggles
  // -------------------------------------------------------------------------

  _toggleReveal(key) {
    this._revealMap = { ...this._revealMap, [key]: !this._revealMap[key] };
    this.requestUpdate();
  }

  _isRevealed(key) { return !!this._revealMap[key]; }

  // -------------------------------------------------------------------------
  // Toast helpers
  // -------------------------------------------------------------------------

  _toast(message, type = "info") {
    const id = Date.now() + Math.random();
    this._toasts = [...this._toasts, { id, message, type }];
    this.requestUpdate();
    setTimeout(() => {
      this._toasts = this._toasts.filter(t => t.id !== id);
      this.requestUpdate();
    }, 4000);
  }

  // -------------------------------------------------------------------------
  // Display helpers
  // -------------------------------------------------------------------------

  _lockDisplayName(entityId) {
    if (this.hass && this.hass.states && this.hass.states[entityId]) {
      return this.hass.states[entityId].attributes.friendly_name || entityId;
    }
    return entityId;
  }

  _overallStatusBadge() {
    if (this._pushing) return { label: "Syncing…", cls: "pushing" };
    const entries = Object.values(this._status);
    if (!entries.length) return { label: "No Locks", cls: "" };
    if (entries.every(s => s.state === "synced")) return { label: "All Synced", cls: "synced" };
    if (entries.some(s => s.failed_count > 0)) return { label: "Errors", cls: "error" };
    return { label: "Out of Sync", cls: "out_of_sync" };
  }

  _isSlotEmpty(slot) {
    return !slot.label && !slot.long_code && !slot.short_code;
  }

  _isSlotDirty(slotNumber) {
    return Object.values(this._status).some(
      s => Array.isArray(s.dirty_slots) && s.dirty_slots.includes(slotNumber)
    );
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  render() {
    if (this._loading) {
      return html`
        ${this._renderToasts()}
        <div class="loading-container">
          <div class="spinner"></div>
          <span>Loading SlotSentry…</span>
        </div>
      `;
    }

    if (this._error) {
      return html`
        ${this._renderToasts()}
        <div class="error-container">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
          </svg>
          <span>${this._error}</span>
          <button class="btn btn-save" @click="${() => this._init()}">Retry</button>
        </div>
      `;
    }

    const badge = this._overallStatusBadge();

    return html`
      ${this._renderToasts()}

      <div class="header">
        <h1>
          <svg class="header-icon" viewBox="0 0 24 24">
            <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
          </svg>
          SlotSentry
        </h1>
        <div class="header-actions">
          <span class="status-badge ${badge.cls}">${badge.label}</span>
          <button
            class="btn btn-primary"
            ?disabled="${this._pushing}"
            @click="${() => this._pushAll()}"
          >
            ${this._pushing
              ? html`<div class="spinner" style="width:14px;height:14px;border-width:2px;"></div> Pushing…`
              : html`
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
                </svg>
                Push All
              `}
          </button>
        </div>
      </div>

      <div class="content">
        ${this._pushing ? html`
          <div class="push-progress-bar">
            <div class="spinner"></div>
            <span>${this._pushProgress}</span>
          </div>
        ` : ""}

        <p class="section-title">Slots (${this._slots.length})</p>
        ${this._renderSlotTable()}

        <p class="section-title" style="margin-top:28px;">Lock Status</p>
        ${this._renderStatusSection()}
      </div>
    `;
  }

  _renderSlotTable() {
    if (!this._slots.length) {
      return html`
        <div class="slot-card" style="padding:20px;color:var(--secondary-text-color,#727272);font-style:italic;">
          No slots configured. Check your SlotSentry integration settings.
        </div>
      `;
    }

    return html`
      <div class="slot-card">
        <div class="slot-table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Label</th>
                <th>Long Code</th>
                <th>Short Code</th>
                <th>Enabled</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${this._slots.map(slot => this._renderSlotRow(slot))}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  _renderSlotRow(slot) {
    const n    = slot.slot_number;
    const vals = this._editValues[n] || {
      label: slot.label || "", long_code: slot.long_code || "",
      short_code: slot.short_code || "", enabled: slot.enabled ?? true,
    };
    const saving   = !!this._savingSlots[n];
    const deleting = !!this._deletingSlots[n];
    const dirty    = this._isSlotDirty(n);
    const isEmpty  = this._isSlotEmpty(slot);

    const longKey  = `long-${n}`;
    const shortKey = `short-${n}`;

    return html`
      <tr class="${dirty ? "slot-dirty" : ""} ${isEmpty ? "empty-slot" : ""}">
        <td class="slot-num">${n}</td>

        <td>
          <input
            class="slot-input"
            type="text"
            placeholder="Label"
            .value="${vals.label}"
            @input="${e => this._onFieldInput(n, "label", e.target.value)}"
          />
        </td>

        <td>
          <div class="code-cell">
            <input
              class="slot-input"
              type="${this._isRevealed(longKey) ? "text" : "password"}"
              placeholder="Long code"
              autocomplete="off"
              .value="${vals.long_code}"
              @input="${e => this._onFieldInput(n, "long_code", e.target.value)}"
            />
            <button
              class="reveal-btn"
              title="${this._isRevealed(longKey) ? "Hide" : "Reveal"}"
              @click="${() => this._toggleReveal(longKey)}"
            >
              ${this._isRevealed(longKey) ? this._iconEyeOff() : this._iconEye()}
            </button>
          </div>
        </td>

        <td>
          <div class="code-cell">
            <input
              class="slot-input"
              type="${this._isRevealed(shortKey) ? "text" : "password"}"
              placeholder="Short code"
              autocomplete="off"
              .value="${vals.short_code}"
              @input="${e => this._onFieldInput(n, "short_code", e.target.value)}"
            />
            <button
              class="reveal-btn"
              title="${this._isRevealed(shortKey) ? "Hide" : "Reveal"}"
              @click="${() => this._toggleReveal(shortKey)}"
            >
              ${this._isRevealed(shortKey) ? this._iconEyeOff() : this._iconEye()}
            </button>
          </div>
        </td>

        <td style="text-align:center;">
          <input
            class="enabled-toggle"
            type="checkbox"
            .checked="${!!vals.enabled}"
            @change="${e => this._onEnabledChange(n, e.target.checked)}"
          />
        </td>

        <td>
          <div class="actions-cell">
            <button
              class="btn btn-save"
              ?disabled="${saving || deleting}"
              @click="${() => this._saveSlot(n)}"
            >
              ${saving
                ? html`<div class="spinner" style="width:12px;height:12px;border-width:2px;"></div>`
                : "Save"}
            </button>
            <button
              class="btn btn-delete"
              ?disabled="${saving || deleting}"
              @click="${() => this._deleteSlot(n)}"
            >
              ${deleting
                ? html`<div class="spinner" style="width:12px;height:12px;border-width:2px;"></div>`
                : "Clear"}
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  _renderStatusSection() {
    const entries = Object.entries(this._status);

    if (!entries.length) {
      return html`<p class="no-locks">No lock status available. Push to populate.</p>`;
    }

    return html`
      <div class="status-grid">
        ${entries.map(([lockEntity, info]) => this._renderLockCard(lockEntity, info))}
      </div>
    `;
  }

  _renderLockCard(lockEntity, info) {
    const name = this._lockDisplayName(lockEntity);
    const state = info.state || "uncertain";
    const pushing = !!this._pushingLocks[lockEntity];

    return html`
      <div class="lock-card ${state}">
        <div class="lock-name">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0;opacity:0.7;">
            <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
          </svg>
          <span title="${lockEntity}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</span>
          <span class="lock-state-pill ${state}">${state.replace("_", " ")}</span>
        </div>

        <div class="lock-counts">
          <span class="lock-count-item">
            <span class="dot dot-synced"></span>
            ${info.synced_count ?? 0} synced
          </span>
          <span class="lock-count-item">
            <span class="dot dot-failed"></span>
            ${info.failed_count ?? 0} failed
          </span>
          <span class="lock-count-item">
            <span class="dot dot-uncertain"></span>
            ${info.uncertain_count ?? 0} uncertain
          </span>
          ${info.dirty_slots && info.dirty_slots.length ? html`
            <span class="lock-count-item">
              <span class="dot dot-dirty"></span>
              ${info.dirty_slots.length} dirty
            </span>
          ` : ""}
        </div>

        ${info.dirty_slots && info.dirty_slots.length ? html`
          <div class="dirty-slots">
            Pending slots: ${info.dirty_slots.slice(0, 10).join(", ")}${info.dirty_slots.length > 10 ? ` +${info.dirty_slots.length - 10} more` : ""}
          </div>
        ` : ""}

        <div class="lock-actions">
          <button
            class="btn btn-push-lock"
            ?disabled="${pushing || this._pushing}"
            @click="${() => this._pushLock(lockEntity)}"
          >
            ${pushing
              ? html`<div class="spinner" style="width:12px;height:12px;border-width:2px;"></div> Pushing…`
              : html`
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
                </svg>
                Push Lock
              `}
          </button>
        </div>
      </div>
    `;
  }

  _renderToasts() {
    if (!this._toasts.length) return "";
    return html`
      <div class="toast-container">
        ${this._toasts.map(t => html`
          <div class="toast ${t.type}">${t.message}</div>
        `)}
      </div>
    `;
  }

  // -------------------------------------------------------------------------
  // SVG icons (inline)
  // -------------------------------------------------------------------------

  _iconEye() {
    return html`
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
      </svg>
    `;
  }

  _iconEyeOff() {
    return html`
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
      </svg>
    `;
  }
}

// ---------------------------------------------------------------------------
// Register the custom element
// ---------------------------------------------------------------------------

if (!customElements.get("slotsentry-panel")) {
  customElements.define("slotsentry-panel", SlotSentryPanel);
}
