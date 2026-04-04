/**
 * SlotSentry Panel — HA sidebar frontend
 * Custom element: slotsentry-panel
 * Version: 2026.4.0a11
 * Revision: 2.3
 *
 * Copyright (c) 2026 Chris Caho
 * SPDX-License-Identifier: MIT
 * Co-authored by Claude Code (Anthropic) under direction of Chris Caho.
 *
 * Pure vanilla web component — no LitElement dependency.
 * Uses innerHTML + event delegation for reliable rendering.
 *
 * WebSocket commands used:
 *   slotsentry/get_slots   — load all slots
 *   slotsentry/set_slot    — save a slot
 *   slotsentry/delete_slot — clear a slot
 *   slotsentry/push_all    — push all dirty slots to all locks
 *   slotsentry/push_lock   — push all dirty slots to one lock
 *   slotsentry/get_status  — per-lock sync summary
 */

class SlotSentryPanel extends HTMLElement {

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    this._entryId = null;
    this._config = null;   // config entry data (locks, code_length_mode, etc.)
    this._slots = [];
    this._status = {};
    this._loading = true;
    this._pushing = false;
    this._pushProgress = "";
    this._toasts = [];
    this._revealMap = {};
    this._savingSlots = {};
    this._deletingSlots = {};
    this._pushingLocks = {};
    this._error = null;
    this._editValues = {};
    this._pushPollId = null;
    this._pushPollStart = 0;
    this._initStarted = false;
    this._renderScheduled = false;
    this._updateAll = false;
    this._dirty = false;
    this._eventsBound = false;
    this._savingAll = false;
    this._nextToastId = 0;
  }

  set hass(v) {
    this._hass = v;
    if (v && !this._initStarted) {
      this._initStarted = true;
      this._init();
    }
  }
  get hass() { return this._hass; }

  set panel(v) { this._panel = v; }
  get panel() { return this._panel; }

  connectedCallback() {
    if (!this._eventsBound) {
      this._eventsBound = true;
      this._bindEvents();
    }
    if (this._hass && !this._initStarted) {
      this._initStarted = true;
      this._init();
    }
  }

  disconnectedCallback() {
    this._stopPushPoll();
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  get _isDual() {
    return this._config && this._config.code_length_mode === "dual";
  }

  get _lockEntities() {
    return (this._config && this._config.lock_entities) || [];
  }

  _lockNames() {
    return this._lockEntities.map(eid => {
      if (this._hass && this._hass.states && this._hass.states[eid]) {
        return this._hass.states[eid].attributes.friendly_name || eid;
      }
      return eid;
    });
  }

  _modeSummary() {
    if (!this._config) return "";
    if (this._isDual) {
      const l = this._config.code_length_2 || "?";
      const s = this._config.code_length_1 || "?";
      return "Code 1: " + s + "-digit / Code 2: " + l + "-digit";
    }
    const c = this._config.code_length_1 || this._config.code_length_2 || "?";
    return c + "-digit";
  }

  _scheduleRender() {
    if (this._renderScheduled) return;
    this._renderScheduled = true;
    requestAnimationFrame(() => {
      this._renderScheduled = false;
      this._render();
    });
  }

  _esc(str) {
    if (str == null) return "";
    const d = document.createElement("div");
    d.textContent = String(str);
    return d.innerHTML;
  }

  // ---------------------------------------------------------------------------
  // Initialisation
  // ---------------------------------------------------------------------------

  async _init() {
    this._loading = true;
    this._error = null;
    this._scheduleRender();

    try {
      await this._discoverEntryId();
    } catch (err) {
      this._error = "Failed to discover config entry: " + (err.message || err);
      this._loading = false;
      this._scheduleRender();
      return;
    }

    if (!this._entryId) {
      this._error = "No SlotSentry config entry found. Please set up the integration first.";
      this._loading = false;
      this._scheduleRender();
      return;
    }

    await this._refresh();
    this._loading = false;
    this._scheduleRender();
  }

  async _discoverEntryId() {
    if (this._panel && this._panel.config && this._panel.config.entry_id) {
      this._entryId = this._panel.config.entry_id;
    }
    // Discover entry ID via config_entries/get if not already known
    if (!this._entryId) {
      const entries = await this._hass.callWS({ type: "config_entries/get", domain: "slotsentry" });
      if (entries && entries.length > 0) {
        this._entryId = entries[0].entry_id;
      }
    }
    // Load config data via our custom WS command (config_entries/get doesn't expose data)
    if (this._entryId) {
      try {
        const result = await this._hass.callWS({
          type: "slotsentry/get_config",
          entry_id: this._entryId,
        });
        this._config = result.config || {};
      } catch (err) {
        this._config = {};
      }
    }
  }

  async _refresh() {
    await Promise.all([this._loadSlots(), this._loadStatus()]);
  }

  async _loadSlots() {
    try {
      const result = await this._hass.callWS({
        type: "slotsentry/get_slots",
        entry_id: this._entryId,
      });
      this._slots = result.slots || [];
      const next = { ...this._editValues };
      for (const slot of this._slots) {
        if (!next[slot.slot_number]) {
          next[slot.slot_number] = {
            label: slot.label || "",
            code_1: slot.code_1 || "",
            code_2: slot.code_2 || "",
            enabled: slot.enabled ?? false,
          };
        }
      }
      this._editValues = next;
      this._scheduleRender();
    } catch (err) {
      this._toast("Failed to load slots: " + (err.message || err), "error");
    }
  }

  async _loadStatus() {
    try {
      const result = await this._hass.callWS({
        type: "slotsentry/get_status",
        entry_id: this._entryId,
      });
      this._status = result.status || {};
      this._scheduleRender();
    } catch (err) {
      this._status = {};
      this._scheduleRender();
    }
  }

  // ---------------------------------------------------------------------------
  // Dirty tracking
  // ---------------------------------------------------------------------------

  _checkDirty() {
    const wasDirty = this._dirty;
    if (this._updateAll) { this._dirty = true; }
    else {
      this._dirty = false;
      for (const slot of this._slots) {
        const n = slot.slot_number;
        const vals = this._editValues[n];
        if (!vals) continue;
        if (vals.label !== (slot.label || "") ||
            vals.code_1 !== (slot.code_1 || "") ||
            vals.code_2 !== (slot.code_2 || "") ||
            vals.enabled !== (slot.enabled ?? false)) {
          this._dirty = true;
          break;
        }
      }
    }
    if (this._dirty !== wasDirty) this._scheduleRender();
  }

  _isRowDirty(slot) {
    const n = slot.slot_number;
    const vals = this._editValues[n];
    if (!vals) return false;
    return vals.label !== (slot.label || "") ||
      vals.code_1 !== (slot.code_1 || "") ||
      vals.code_2 !== (slot.code_2 || "") ||
      vals.enabled !== (slot.enabled ?? false);
  }

  // ---------------------------------------------------------------------------
  // Slot actions
  // ---------------------------------------------------------------------------

  _onFieldInput(slotNumber, field, value) {
    const cur = this._editValues[slotNumber] || {};
    this._editValues = { ...this._editValues, [slotNumber]: { ...cur, [field]: value } };
    this._checkDirty();
    // Don't full re-render on keystrokes — just track state
  }

  _onEnabledChange(slotNumber, checked) {
    const cur = this._editValues[slotNumber] || {};
    this._editValues = { ...this._editValues, [slotNumber]: { ...cur, enabled: checked } };
    this._checkDirty();
    this._scheduleRender();
  }

  async _saveSlot(slotNumber) {
    const vals = this._editValues[slotNumber];
    if (!vals) return;

    this._savingSlots = { ...this._savingSlots, [slotNumber]: true };
    this._scheduleRender();

    try {
      await this._hass.callWS({
        type: "slotsentry/set_slot",
        entry_id: this._entryId,
        slot_number: slotNumber,
        label: vals.label || "",
        code_1: vals.code_1 || "",
        code_2: vals.code_2 || "",
        enabled: !!vals.enabled,
      });
      this._toast("Slot " + slotNumber + " saved.", "success");
      // Clear cached edit for this slot so it reloads fresh
      const ev = { ...this._editValues };
      delete ev[slotNumber];
      this._editValues = ev;
      await this._refresh();
    } catch (err) {
      this._toast("Save failed: " + (err.message || err), "error");
    } finally {
      const s = { ...this._savingSlots };
      delete s[slotNumber];
      this._savingSlots = s;
      this._checkDirty();
      this._scheduleRender();
    }
  }

  async _deleteSlot(slotNumber) {
    if (!window.confirm("Clear slot " + slotNumber + "? This will remove the label and codes.")) return;

    this._deletingSlots = { ...this._deletingSlots, [slotNumber]: true };
    this._scheduleRender();

    try {
      await this._hass.callWS({
        type: "slotsentry/delete_slot",
        entry_id: this._entryId,
        slot_number: slotNumber,
      });
      this._toast("Slot " + slotNumber + " cleared.", "success");
      const ev = { ...this._editValues };
      delete ev[slotNumber];
      this._editValues = ev;
      await this._refresh();
    } catch (err) {
      this._toast("Delete failed: " + (err.message || err), "error");
    } finally {
      const s = { ...this._deletingSlots };
      delete s[slotNumber];
      this._deletingSlots = s;
      this._checkDirty();
      this._scheduleRender();
    }
  }

  async _saveAll() {
    // Save every slot that has edits (or all if _updateAll)
    const toSave = [];
    for (const slot of this._slots) {
      const n = slot.slot_number;
      const vals = this._editValues[n];
      if (!vals) continue;
      if (this._updateAll || this._isRowDirty(slot)) {
        toSave.push({ slot_number: n, ...vals });
      }
    }

    if (!toSave.length) {
      this._toast("No changes to save.", "info");
      return;
    }

    this._savingAll = true;
    this._pushProgress = "Saving " + toSave.length + " slot(s)\u2026";
    this._scheduleRender();

    let saved = 0;
    let failed = 0;
    for (const s of toSave) {
      try {
        await this._hass.callWS({
          type: "slotsentry/set_slot",
          entry_id: this._entryId,
          slot_number: s.slot_number,
          label: s.label || "",
          code_1: s.code_1 || "",
          code_2: s.code_2 || "",
          enabled: !!s.enabled,
        });
        saved++;
      } catch (err) {
        failed++;
      }
    }

    this._savingAll = false;
    this._pushProgress = "";
    this._updateAll = false;

    if (failed) {
      this._toast("Saved " + saved + " slot(s), " + failed + " failed.", "error");
    } else {
      this._toast("Saved " + saved + " slot(s).", "success");
    }

    // Clear all cached edits and reload
    this._editValues = {};
    await this._refresh();
    this._checkDirty();
    this._scheduleRender();
  }

  _discardAll() {
    this._editValues = {};
    this._updateAll = false;
    // Re-seed from current slot data
    for (const slot of this._slots) {
      this._editValues[slot.slot_number] = {
        label: slot.label || "",
        code_1: slot.code_1 || "",
        code_2: slot.code_2 || "",
        enabled: slot.enabled ?? false,
      };
    }
    this._dirty = false;
    this._scheduleRender();
  }

  // ---------------------------------------------------------------------------
  // Push actions
  // ---------------------------------------------------------------------------

  async _pushAll() {
    if (this._pushing) return;
    this._pushing = true;
    this._pushProgress = "Pushing to all locks\u2026";
    this._scheduleRender();

    try {
      await this._hass.callWS({ type: "slotsentry/push_all", entry_id: this._entryId });
      this._toast("Push complete for all locks.", "success");
    } catch (err) {
      this._toast("Push failed: " + (err.message || err), "error");
    } finally {
      this._pushing = false;
      this._pushProgress = "";
      await this._refresh();
      this._scheduleRender();
    }
  }

  async _pushLock(lockEntity) {
    if (this._pushingLocks[lockEntity]) return;
    this._pushingLocks = { ...this._pushingLocks, [lockEntity]: true };
    this._scheduleRender();

    try {
      await this._hass.callWS({
        type: "slotsentry/push_lock",
        entry_id: this._entryId,
        lock_entity: lockEntity,
      });
      this._toast("Push complete for " + this._lockDisplayName(lockEntity) + ".", "success");
    } catch (err) {
      this._toast("Push failed: " + (err.message || err), "error");
    } finally {
      const s = { ...this._pushingLocks };
      delete s[lockEntity];
      this._pushingLocks = s;
      await this._refresh();
      this._scheduleRender();
    }
  }

  _allLocksSynced() {
    const entries = Object.values(this._status);
    return entries.length > 0 && entries.every(s => s.state === "synced");
  }

  // ---------------------------------------------------------------------------
  // Reveal toggles
  // ---------------------------------------------------------------------------

  _toggleReveal(key) {
    this._revealMap = { ...this._revealMap, [key]: !this._revealMap[key] };
    this._scheduleRender();
  }

  // ---------------------------------------------------------------------------
  // Toast helpers
  // ---------------------------------------------------------------------------

  _toast(message, type) {
    const id = Date.now() + Math.random();
    this._toasts = [...this._toasts, { id, message, type: type || "info" }];
    this._scheduleRender();
    setTimeout(() => {
      this._toasts = this._toasts.filter(t => t.id !== id);
      this._scheduleRender();
    }, 4000);
  }

  // ---------------------------------------------------------------------------
  // Display helpers
  // ---------------------------------------------------------------------------

  _lockDisplayName(entityId) {
    if (this._hass && this._hass.states && this._hass.states[entityId]) {
      return this._hass.states[entityId].attributes.friendly_name || entityId;
    }
    return entityId;
  }

  _overallStatusBadge() {
    if (this._pushing) return { label: "Syncing\u2026", cls: "pushing" };
    const entries = Object.values(this._status);
    if (!entries.length) return { label: "No Locks", cls: "" };
    if (entries.every(s => s.state === "synced")) return { label: "All Synced", cls: "synced" };
    if (entries.some(s => s.failed_count > 0)) return { label: "Errors", cls: "error" };
    if (entries.some(s => s.state === "pending")) return { label: "Pending Sync", cls: "out_of_sync" };
    return { label: "Out of Sync", cls: "out_of_sync" };
  }

  _isSlotEmpty(slot) {
    return !slot.label && !slot.code_1 && !slot.code_2;
  }

  _isSlotDirtyOnLock(slotNumber) {
    return Object.values(this._status).some(
      s => Array.isArray(s.dirty_slots) && s.dirty_slots.includes(slotNumber)
    );
  }

  _getSlotSyncStatus(slotNumber) {
    const entries = Object.values(this._status);
    if (!entries.length) return { cls: "", tip: "No status" };
    const dirty = this._isSlotDirtyOnLock(slotNumber);
    if (dirty) return { cls: "sync-dirty", tip: "Out of sync — needs push" };
    return { cls: "sync-ok", tip: "Synced" };
  }

  _buildErrorSummary() {
    const lines = [];
    for (const [lockEntity, info] of Object.entries(this._status)) {
      if (info.failed_count > 0 || info.pending_count > 0 || info.uncertain_count > 0) {
        const name = this._lockDisplayName(lockEntity);
        const parts = [];
        if (info.failed_count) parts.push(info.failed_count + " failed");
        if (info.pending_count) parts.push(info.pending_count + " pending");
        if (info.uncertain_count) parts.push(info.uncertain_count + " uncertain");
        if (info.dirty_slots && info.dirty_slots.length) {
          parts.push("slots: " + info.dirty_slots.slice(0, 10).join(", "));
        }
        lines.push(name + ": " + parts.join(", "));
      }
    }
    return lines.length ? lines.join("\n") : "No issues found.";
  }

  // ---------------------------------------------------------------------------
  // SVG icons
  // ---------------------------------------------------------------------------

  _iconEyeSVG() {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>';
  }

  _iconEyeOffSVG() {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>';
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  _render() {
    const root = this.shadowRoot;

    if (this._loading) {
      root.innerHTML = this._styles() +
        '<div class="loading-container"><div class="spinner"></div><span>Loading SlotSentry\u2026</span></div>' +
        this._renderToastsHTML();
      return;
    }

    if (this._error) {
      root.innerHTML = this._styles() +
        '<div class="error-container">' +
          '<svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>' +
          '<span>' + this._esc(this._error) + '</span>' +
          '<button class="btn btn-save" data-action="retry">Retry</button>' +
        '</div>' + this._renderToastsHTML();
      return;
    }

    const badge = this._overallStatusBadge();
    const lockNames = this._lockNames().join(" \u2022 ");
    const version = "v2026.4.0a11";
    const modeName = this._isDual ? "Dual" : "Single";

    // Error badge: only show if there are actual errors; make it clickable
    let badgeHTML = "";
    if (badge.cls === "error") {
      badgeHTML = `<button class="status-badge ${this._esc(badge.cls)}" data-action="show-errors" title="Click for details">${this._esc(badge.label)}</button>`;
    } else if (badge.label) {
      badgeHTML = `<span class="status-badge ${this._esc(badge.cls)}">${this._esc(badge.label)}</span>`;
    }

    root.innerHTML = this._styles() + `
      <div class="header">
        <div class="header-left">
          <h1>
            <svg class="header-icon" viewBox="0 0 24 24">
              <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
            </svg>
            SlotSentry \u2014 Slot Manager
            <span class="version">${this._esc(version)}</span>
          </h1>
          <div class="header-info">
            <span class="header-detail">Locks: ${this._esc(lockNames)}</span>
            <span class="header-detail">Mode: ${this._esc(modeName)} &nbsp; Code lengths: ${this._esc(this._modeSummary())}</span>
          </div>
        </div>
        <div class="header-actions">
          ${badgeHTML}
          <button class="btn btn-primary" data-action="push-all" ${this._pushing || this._savingAll ? "disabled" : ""}>
            ${this._pushing
              ? '<div class="spinner-sm"></div> Pushing\u2026'
              : '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:middle;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg> Push Changes'}
          </button>
        </div>
      </div>

      <div class="content">
        ${this._pushing || this._savingAll ? '<div class="push-progress-bar"><div class="spinner-sm"></div><span>' + this._esc(this._pushProgress) + '</span></div>' : ''}

        <p class="section-title">Slots (${this._slots.length})</p>
        ${this._renderSlotTableHTML()}

        <div class="bottom-bar">
          <label class="update-all-label">
            <input type="checkbox" data-action="update-all" ${this._updateAll ? "checked" : ""} />
            Update All Slots
          </label>
          <div class="bottom-actions">
            ${this._dirty
              ? '<button class="btn btn-discard" data-action="discard">Discard</button><button class="btn btn-save" data-action="save-all">Save</button>'
              : ''}
          </div>
        </div>

        <p class="section-title" style="margin-top:28px;">Lock Status</p>
        ${this._renderStatusSectionHTML()}
      </div>
    ` + this._renderToastsHTML();

    this._restoreInputValues();
  }

  _renderSlotTableHTML() {
    if (!this._slots.length) {
      return '<div class="slot-card" style="padding:20px;color:var(--secondary-text-color,#727272);font-style:italic;">No slots available. The integration may need to be reconfigured.</div>';
    }

    const dual = this._isDual;
    const code2Len = (this._config && this._config.code_length_2) || "?";
    const code1Len = (this._config && this._config.code_length_1) || "?";
    const singleLen = (this._config && (this._config.code_length_1 || this._config.code_length_2)) || "?";
    let headerCols = '<th class="col-num">#</th><th class="col-on">On</th><th>Label</th>';
    if (dual) {
      headerCols += `<th>Code 1 (${this._esc(code1Len)}-digit)</th><th>Code 2 (${this._esc(code2Len)}-digit)</th>`;
    } else {
      headerCols += `<th>Code (${this._esc(singleLen)}-digit)</th>`;
    }
    headerCols += '<th class="col-status">Status</th><th>Actions</th>';

    let rows = "";
    for (const slot of this._slots) {
      rows += this._renderSlotRowHTML(slot);
    }

    return `
      <div class="slot-card">
        <div class="slot-table-wrap">
          <table>
            <thead><tr>${headerCols}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  _renderSlotRowHTML(slot) {
    const n = slot.slot_number;
    const vals = this._editValues[n] || {
      label: slot.label || "", code_1: slot.code_1 || "",
      code_2: slot.code_2 || "", enabled: slot.enabled ?? false,
    };
    const saving = !!this._savingSlots[n];
    const deleting = !!this._deletingSlots[n];
    const rowDirty = this._isRowDirty(slot);
    const lockDirty = this._isSlotDirtyOnLock(n);
    const isEmpty = this._isSlotEmpty(slot);
    const disabled = saving || deleting ? "disabled" : "";
    const dual = this._isDual;

    let classes = "";
    if (rowDirty) classes += " slot-edited";
    if (lockDirty) classes += " slot-dirty";
    if (isEmpty) classes += " empty-slot";
    if (!vals.enabled) classes += " slot-disabled";

    const code2Len = (this._config && this._config.code_length_2) || "";
    const code1Len = (this._config && this._config.code_length_1) || "";
    const singleLen = (this._config && (this._config.code_length_1 || this._config.code_length_2)) || "";
    const secure = !!(this._config && this._config.secure_mode);

    let codeColumns = "";
    if (dual) {
      const longRevealed = !secure || !!this._revealMap["long-" + n];
      const shortRevealed = !secure || !!this._revealMap["short-" + n];
      const revealBtn1 = secure
        ? `<button class="reveal-btn" data-action="reveal" data-key="long-${n}"
            title="${longRevealed ? "Hide" : "Reveal"}">${longRevealed ? this._iconEyeOffSVG() : this._iconEyeSVG()}</button>`
        : "";
      const revealBtn2 = secure
        ? `<button class="reveal-btn" data-action="reveal" data-key="short-${n}"
            title="${shortRevealed ? "Hide" : "Reveal"}">${shortRevealed ? this._iconEyeOffSVG() : this._iconEyeSVG()}</button>`
        : "";
      codeColumns = `
        <td>
          <div class="code-cell">
            <input class="slot-input" type="${longRevealed ? "text" : "password"}"
              placeholder="${code1Len ? code1Len + " digits" : "Code 1"}" autocomplete="off"
              data-slot="${n}" data-field="code_1" />${revealBtn1}
          </div>
        </td>
        <td>
          <div class="code-cell">
            <input class="slot-input" type="${shortRevealed ? "text" : "password"}"
              placeholder="${code2Len ? code2Len + " digits" : "Code 2"}" autocomplete="off"
              data-slot="${n}" data-field="code_2" />${revealBtn2}
          </div>
        </td>`;
    } else {
      const revealed = !secure || !!this._revealMap["code-" + n];
      const revealBtn = secure
        ? `<button class="reveal-btn" data-action="reveal" data-key="code-${n}"
            title="${revealed ? "Hide" : "Reveal"}">${revealed ? this._iconEyeOffSVG() : this._iconEyeSVG()}</button>`
        : "";
      codeColumns = `
        <td>
          <div class="code-cell">
            <input class="slot-input" type="${revealed ? "text" : "password"}"
              placeholder="${singleLen ? singleLen + " digits" : "Code"}" autocomplete="off"
              data-slot="${n}" data-field="code_1" />${revealBtn}
          </div>
        </td>`;
    }

    // Slot sync status indicator
    const syncStatus = this._getSlotSyncStatus(n);

    return `
      <tr class="${classes.trim()}">
        <td class="slot-num">${n}</td>
        <td class="col-on">
          <input class="enabled-toggle" type="checkbox"
            data-slot="${n}" data-field="enabled" ${vals.enabled ? "checked" : ""} />
        </td>
        <td>
          <input class="slot-input" type="text" placeholder="Label"
            data-slot="${n}" data-field="label" />
        </td>
        ${codeColumns}
        <td class="col-status">
          <span class="slot-sync-dot ${this._esc(syncStatus.cls)}" title="${this._esc(syncStatus.tip)}"></span>
        </td>
        <td>
          <div class="actions-cell">
            <button class="btn btn-save btn-sm" data-action="save" data-slot="${n}" ${disabled}>
              ${saving ? '<div class="spinner-xs"></div>' : "Save"}
            </button>
            <button class="btn btn-delete btn-sm" data-action="delete" data-slot="${n}" ${disabled}>
              ${deleting ? '<div class="spinner-xs"></div>' : "Clear"}
            </button>
          </div>
        </td>
      </tr>`;
  }

  _renderStatusSectionHTML() {
    const entries = Object.entries(this._status);
    if (!entries.length) {
      return '<p class="no-locks">No lock status available. Push codes to populate.</p>';
    }
    let cards = "";
    for (const [lockEntity, info] of entries) {
      cards += this._renderLockCardHTML(lockEntity, info);
    }
    return '<div class="status-grid">' + cards + '</div>';
  }

  _renderLockCardHTML(lockEntity, info) {
    const name = this._lockDisplayName(lockEntity);
    const state = info.state || "uncertain";
    const pushing = !!this._pushingLocks[lockEntity];

    let dirtyCountHTML = "";
    let dirtyListHTML = "";
    if (info.dirty_slots && info.dirty_slots.length) {
      dirtyCountHTML = '<span class="lock-count-item"><span class="dot dot-dirty"></span>' + info.dirty_slots.length + ' dirty</span>';
      const shown = info.dirty_slots.slice(0, 10).join(", ");
      const extra = info.dirty_slots.length > 10 ? (" +" + (info.dirty_slots.length - 10) + " more") : "";
      dirtyListHTML = '<div class="dirty-slots">Pending: ' + this._esc(shown + extra) + '</div>';
    }

    return `
      <div class="lock-card ${this._esc(state)}">
        <div class="lock-name">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0;opacity:0.7;">
            <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
          </svg>
          <span title="${this._esc(lockEntity)}" class="lock-name-text">${this._esc(name)}</span>
          <span class="lock-state-pill ${this._esc(state)}">${this._esc(state.replace(/_/g, " "))}</span>
        </div>
        <div class="lock-counts">
          <span class="lock-count-item"><span class="dot dot-synced"></span>${info.synced_count ?? 0} synced</span>
          ${(info.failed_count ?? 0) > 0 ? '<span class="lock-count-item"><span class="dot dot-failed"></span>' + info.failed_count + ' failed</span>' : ""}
          ${(info.pending_count ?? 0) > 0 ? '<span class="lock-count-item"><span class="dot dot-dirty"></span>' + info.pending_count + ' pending</span>' : ""}
          ${(info.uncertain_count ?? 0) > 0 ? '<span class="lock-count-item"><span class="dot dot-uncertain"></span>' + info.uncertain_count + ' uncertain</span>' : ""}
          ${dirtyCountHTML}
        </div>
        ${dirtyListHTML}
        <div class="lock-actions">
          <button class="btn btn-push-lock" data-action="push-lock" data-lock="${this._esc(lockEntity)}"
            ${pushing || this._pushing ? "disabled" : ""}>
            ${pushing
              ? '<div class="spinner-xs"></div> Pushing\u2026'
              : '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:middle;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg> Push Lock'}
          </button>
        </div>
      </div>`;
  }

  _renderToastsHTML() {
    if (!this._toasts.length) return "";
    let toasts = "";
    for (const t of this._toasts) {
      toasts += '<div class="toast ' + this._esc(t.type) + '">' + this._esc(t.message) + '</div>';
    }
    return '<div class="toast-container">' + toasts + '</div>';
  }

  // ---------------------------------------------------------------------------
  // Event binding via delegation
  // ---------------------------------------------------------------------------

  _bindEvents() {
    const root = this.shadowRoot;

    root.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;
      const action = btn.dataset.action;
      if (action === "retry") { this._initStarted = false; this._init(); }
      else if (action === "push-all") { this._pushAll(); }
      else if (action === "save") { this._saveSlot(parseInt(btn.dataset.slot, 10)); }
      else if (action === "delete") { this._deleteSlot(parseInt(btn.dataset.slot, 10)); }
      else if (action === "reveal") { this._toggleReveal(btn.dataset.key); }
      else if (action === "push-lock") { this._pushLock(btn.dataset.lock); }
      else if (action === "save-all") { this._saveAll(); }
      else if (action === "discard") { this._discardAll(); }
      else if (action === "show-errors") { window.alert(this._buildErrorSummary()); }
    });

    root.addEventListener("input", (e) => {
      const inp = e.target;
      if (inp.dataset.slot && inp.dataset.field) {
        this._onFieldInput(parseInt(inp.dataset.slot, 10), inp.dataset.field, inp.value);
      }
    });

    root.addEventListener("change", (e) => {
      const inp = e.target;
      if (inp.dataset.slot && inp.dataset.field === "enabled") {
        this._onEnabledChange(parseInt(inp.dataset.slot, 10), inp.checked);
      }
      if (inp.dataset.action === "update-all") {
        this._updateAll = inp.checked;
        this._checkDirty();
        this._scheduleRender();
      }
    });
  }

  _restoreInputValues() {
    const root = this.shadowRoot;
    const inputs = root.querySelectorAll("input[data-slot][data-field]");
    for (const inp of inputs) {
      const n = parseInt(inp.dataset.slot, 10);
      const field = inp.dataset.field;
      const vals = this._editValues[n];
      if (!vals) continue;
      if (field === "enabled") {
        inp.checked = !!vals.enabled;
      } else if (vals[field] !== undefined) {
        inp.value = vals[field];
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Styles
  // ---------------------------------------------------------------------------

  _styles() {
    return `<style>
      :host {
        display: block;
        font-family: var(--paper-font-body1_-_font-family, "Roboto", sans-serif);
        color: var(--primary-text-color, #212121);
        background: var(--primary-background-color, #fafafa);
        min-height: 100vh;
        --ss-accent: var(--primary-color, #03a9f4);
        --ss-accent-text: #fff;
        --ss-success: #4caf50;
        --ss-error: #f44336;
        --ss-warning: #ff9800;
        --ss-uncertain: #9e9e9e;
        --ss-dirty: #ff9800;
        --ss-card-bg: var(--card-background-color, #fff);
        --ss-border: var(--divider-color, #e0e0e0);
        --ss-radius: 12px;
      }

      /* Header */
      .header {
        display: flex; align-items: flex-start; justify-content: space-between;
        padding: 16px 24px;
        background: var(--ss-card-bg);
        border-bottom: 1px solid var(--ss-border);
        position: sticky; top: 0; z-index: 10;
      }
      .header-left { flex: 1; min-width: 0; }
      .header h1 {
        margin: 0; font-size: 20px; font-weight: 500;
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      }
      .header-icon { width: 28px; height: 28px; fill: var(--ss-accent); flex-shrink: 0; }
      .version { font-size: 11px; color: var(--secondary-text-color); font-weight: 400; }
      .header-info {
        display: flex; flex-wrap: wrap; gap: 6px 18px;
        margin-top: 4px; font-size: 12px; color: var(--secondary-text-color);
      }
      .header-detail { white-space: nowrap; }
      .header-actions {
        display: flex; align-items: center; gap: 12px; flex-shrink: 0; margin-left: 16px; margin-top: 4px;
      }

      /* Status badge */
      .status-badge {
        display: inline-block; padding: 3px 10px;
        border-radius: 12px; font-size: 12px; font-weight: 500;
        background: var(--ss-border); color: var(--primary-text-color);
      }
      .status-badge.synced { background: var(--ss-success); color: #fff; }
      .status-badge.error { background: var(--ss-error); color: #fff; cursor: pointer; }
      button.status-badge { border: none; font-family: inherit; }
      .status-badge.out_of_sync { background: var(--ss-warning); color: #fff; }
      .status-badge.pushing { background: var(--ss-accent); color: #fff; }

      /* Buttons */
      .btn {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 6px 14px; border: none; border-radius: 8px;
        font-size: 13px; font-weight: 500; cursor: pointer;
        transition: opacity .15s;
      }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .btn-sm { padding: 4px 10px; font-size: 12px; }
      .btn-primary { background: var(--ss-accent); color: var(--ss-accent-text); }
      .btn-save { background: var(--ss-success); color: #fff; }
      .btn-delete { background: var(--ss-error); color: #fff; }
      .btn-discard { background: var(--ss-uncertain); color: #fff; }
      .btn-push-lock { background: var(--ss-accent); color: var(--ss-accent-text); font-size: 12px; padding: 4px 10px; }

      /* Content */
      .content { padding: 20px 24px 40px; max-width: 1200px; margin: 0 auto; }
      .section-title {
        font-size: 15px; font-weight: 500; margin: 0 0 10px 0;
        color: var(--secondary-text-color, #727272);
      }

      /* Slot table card */
      .slot-card {
        background: var(--ss-card-bg);
        border-radius: var(--ss-radius);
        border: 1px solid var(--ss-border);
        overflow: hidden;
      }
      .slot-table-wrap { overflow-x: auto; max-height: 70vh; overflow-y: auto; }
      table { width: 100%; border-collapse: collapse; font-size: 13px; }
      thead { position: sticky; top: 0; z-index: 2; background: var(--ss-card-bg); }
      th {
        text-align: left; padding: 10px 8px;
        font-weight: 600; font-size: 12px; text-transform: uppercase;
        letter-spacing: 0.5px; color: var(--secondary-text-color, #727272);
        border-bottom: 2px solid var(--ss-border);
      }
      td { padding: 6px 8px; border-bottom: 1px solid var(--ss-border); vertical-align: middle; }
      .col-num { width: 36px; text-align: center; }
      .col-on { width: 40px; text-align: center; }
      .slot-num { font-weight: 600; color: var(--secondary-text-color); text-align: center; }

      tr.slot-edited { background: rgba(255, 235, 59, 0.12); }
      tr.slot-dirty { background: rgba(255, 152, 0, 0.08); }
      tr.empty-slot td { opacity: 0.6; }
      tr.slot-disabled td:not(.slot-num):not(.col-on) { opacity: 0.4; }
      tr:hover { background: rgba(0,0,0,0.02); }

      /* Inputs */
      .slot-input {
        width: 100%; min-width: 60px; padding: 5px 8px;
        border: 1px solid var(--ss-border); border-radius: 6px;
        font-size: 13px; background: var(--primary-background-color, #fafafa);
        color: var(--primary-text-color); box-sizing: border-box;
      }
      .slot-input:focus { outline: none; border-color: var(--ss-accent); }

      .code-cell { display: flex; align-items: center; gap: 4px; }
      .reveal-btn {
        background: none; border: none; cursor: pointer; padding: 4px;
        color: var(--secondary-text-color); display: flex; align-items: center;
        border-radius: 4px; flex-shrink: 0;
      }
      .reveal-btn:hover { background: rgba(0,0,0,0.05); }

      .enabled-toggle { width: 18px; height: 18px; cursor: pointer; accent-color: var(--ss-accent); }
      .col-status { width: 44px; text-align: center; }
      .slot-sync-dot {
        display: inline-block; width: 10px; height: 10px; border-radius: 50%;
        background: var(--ss-uncertain);
      }
      .slot-sync-dot.sync-ok { background: var(--ss-success); }
      .slot-sync-dot.sync-dirty { background: var(--ss-warning); }
      .actions-cell { display: flex; gap: 6px; white-space: nowrap; }

      /* Bottom bar */
      .bottom-bar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 12px 0; margin-top: 8px;
      }
      .update-all-label {
        display: flex; align-items: center; gap: 8px;
        font-size: 13px; cursor: pointer; color: var(--primary-text-color);
      }
      .update-all-label input { width: 16px; height: 16px; accent-color: var(--ss-accent); }
      .bottom-actions { display: flex; gap: 8px; }

      /* Lock status */
      .status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
      .lock-card {
        background: var(--ss-card-bg); border-radius: var(--ss-radius);
        border: 1px solid var(--ss-border); padding: 14px;
        border-left: 4px solid var(--ss-uncertain);
      }
      .lock-card.synced { border-left-color: var(--ss-success); }
      .lock-card.out_of_sync { border-left-color: var(--ss-warning); }
      .lock-card.error, .lock-card.failed { border-left-color: var(--ss-error); }

      .lock-name { display: flex; align-items: center; gap: 8px; font-weight: 500; font-size: 14px; margin-bottom: 8px; }
      .lock-name-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .lock-state-pill {
        font-size: 10px; font-weight: 600; text-transform: uppercase;
        padding: 2px 8px; border-radius: 10px; letter-spacing: 0.3px;
        background: var(--ss-uncertain); color: #fff; flex-shrink: 0;
      }
      .lock-state-pill.synced { background: var(--ss-success); }
      .lock-state-pill.out_of_sync { background: var(--ss-warning); }
      .lock-state-pill.error, .lock-state-pill.failed { background: var(--ss-error); }

      .lock-counts { display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: var(--secondary-text-color); margin-bottom: 8px; }
      .lock-count-item { display: flex; align-items: center; gap: 4px; }
      .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
      .dot-synced { background: var(--ss-success); }
      .dot-failed { background: var(--ss-error); }
      .dot-uncertain { background: var(--ss-uncertain); }
      .dot-dirty { background: var(--ss-dirty); }

      .dirty-slots { font-size: 11px; color: var(--secondary-text-color); margin-bottom: 8px; font-style: italic; }
      .lock-actions { display: flex; justify-content: flex-end; }

      /* Loading / Error */
      .loading-container, .error-container {
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; gap: 14px; padding: 80px 20px;
        color: var(--secondary-text-color);
      }

      /* Push progress */
      .push-progress-bar {
        display: flex; align-items: center; gap: 10px;
        padding: 10px 16px; margin-bottom: 16px;
        background: rgba(3, 169, 244, 0.08);
        border-radius: 8px; font-size: 13px; color: var(--ss-accent);
      }

      /* Spinners */
      .spinner { width: 24px; height: 24px; border: 3px solid var(--ss-border); border-top-color: var(--ss-accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
      .spinner-sm { width: 14px; height: 14px; border: 2px solid var(--ss-border); border-top-color: var(--ss-accent); border-radius: 50%; animation: spin 0.8s linear infinite; display: inline-block; vertical-align: middle; }
      .spinner-xs { width: 12px; height: 12px; border: 2px solid var(--ss-border); border-top-color: var(--ss-accent); border-radius: 50%; animation: spin 0.8s linear infinite; display: inline-block; }
      @keyframes spin { to { transform: rotate(360deg); } }

      /* Toasts */
      .toast-container {
        position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
        z-index: 9999; display: flex; flex-direction: column; gap: 8px;
        align-items: center; pointer-events: none;
      }
      .toast {
        padding: 10px 20px; border-radius: 8px; font-size: 13px;
        color: #fff; pointer-events: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        animation: toastIn 0.3s ease;
      }
      .toast.success { background: var(--ss-success); }
      .toast.error { background: var(--ss-error); }
      .toast.info { background: var(--ss-accent); }
      @keyframes toastIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

      .no-locks { color: var(--secondary-text-color); font-style: italic; }

      @media (max-width: 600px) {
        .header { padding: 12px 14px; flex-direction: column; gap: 8px; }
        .header-actions { margin-left: 0; }
        .header h1 { font-size: 17px; }
        .content { padding: 12px 8px 32px; }
        .status-grid { grid-template-columns: 1fr; }
      }
    </style>`;
  }
}

// Register the custom element
if (!customElements.get("slotsentry-panel")) {
  customElements.define("slotsentry-panel", SlotSentryPanel);
}
