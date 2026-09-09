"use strict";

// components/action_bar.js — GalleryVault Front-end
// Universal batch action bar and task status bar component

(function(global) {
  const BaseComponent = global.BaseComponent || class {
    constructor(container, props = {}) {
      this.container = typeof container === "string" ? document.getElementById(container) : container;
      this.props = props;
      this.state = {};
      this.unsubscribers = [];
      if (this.init) this.init();
    }
    init() {}
    setState(next) { Object.assign(this.state, next); this.render(); }
    setProps(next) { Object.assign(this.props, next); this.render(); }
    render() {}
    bindEvents() {}
    destroy() {
      this.unsubscribers.forEach(fn => { try { fn(); } catch (_) {} });
      this.unsubscribers = [];
    }
  };

  class ActionBarComponent extends BaseComponent {
    constructor(container, props = {}) {
      super(container, props);
    }

    init() {
      this.actions = this.props.actions || [];
      this.filters = this.props.filters || [];
      this.count = this.props.count != null ? this.props.count : 0;
      this.storeKey = this.props.storeKey || null; // e.g., "selFav", "selGalleries"
      this.mode = this.props.mode || "toolbar"; // "toolbar" | "floating"
      this.extraHtml = this.props.extraHtml || "";

      // Subscribe to Store if storeKey provided or store exists
      if (this.storeKey && global.store && typeof global.store.subscribe === "function") {
        const unsub = global.store.subscribe((state) => {
          const targetSet = state[this.storeKey];
          const newCount = targetSet && typeof targetSet.size === "number" ? targetSet.size : (Array.isArray(targetSet) ? targetSet.length : 0);
          if (newCount !== this.count) {
            this.updateCount(newCount);
          }
        });
        this.unsubscribers.push(unsub);
      }
    }

    /**
     * Render action bar into its container.
     */
    render() {
      if (!this.container) return;
      const escape = global.esc || (s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

      const buttonsHtml = this.actions.map(act => {
        const countSuffix = act.showCount !== false && this.count > 0 ? ` (${this.count})` : "";
        const cls = "btn " + (act.primary ? "btn-primary primary" : "btn-secondary secondary") + (act.danger ? " danger" : "") + (act.className ? " " + act.className : "");
        const disabledAttr = (act.requireSelection && this.count === 0) ? " disabled" : "";
        const dataAttrs = act.dataAttrs
          ? Object.entries(act.dataAttrs).map(([k, v]) => ` data-${escape(k)}="${escape(v)}"`).join("")
          : "";
        return `<button class="${cls}" data-action="${escape(act.id || act.action)}"${dataAttrs}${disabledAttr} type="button">${escape(act.label || "")}<span class="action-count">${countSuffix}</span></button>`;
      }).join("");

      const filtersHtml = this.filters.length ? `
        <span class="action-bar-filters">
          ${this.filters.map(f => `<button class="secondary${f.active ? " active-pill" : ""}" data-action="${escape(f.action || "filter")}" data-filter-value="${escape(f.value || "")}" type="button">${escape(f.label)}</button>`).join("")}
        </span>
      ` : "";

      const barClass = this.mode === "floating" ? "action-bar floating-bar" : "toolbar action-bar-toolbar";
      this.container.innerHTML = `
        <div class="${barClass}">
          <div class="action-bar-buttons">
            ${buttonsHtml}
          </div>
          ${filtersHtml}
          ${this.extraHtml}
        </div>
      `;

      this.bindEvents();
    }

    /**
     * Bind DOM click handlers for action buttons.
     */
    bindEvents() {
      if (!this.container) return;
      const btns = this.container.querySelectorAll('[data-action]');
      btns.forEach(btn => {
        const actionId = btn.getAttribute("data-action");
        const actionDef = this.actions.find(a => (a.id || a.action) === actionId);
        if (actionDef && typeof actionDef.onClick === "function") {
          btn.addEventListener("click", (e) => {
            actionDef.onClick(this.count, e, this);
          });
        }
      });
    }

    /**
     * Update selection count and refresh button labels without re-rendering entire markup.
     */
    updateCount(newCount) {
      this.count = Math.max(0, newCount || 0);
      if (!this.container) return;

      this.actions.forEach(act => {
        const actId = act.id || act.action;
        const btn = this.container.querySelector(`[data-action="${actId}"]`);
        if (!btn) return;

        if (act.requireSelection) {
          btn.disabled = this.count === 0;
        }

        const countSpan = btn.querySelector(".action-count");
        if (countSpan) {
          countSpan.textContent = (act.showCount !== false && this.count > 0) ? ` (${this.count})` : "";
        } else {
          const suffix = (act.showCount !== false && this.count > 0) ? ` (${this.count})` : "";
          btn.textContent = (act.label || "") + suffix;
        }
      });

      if (global.store && typeof global.store.emit === "function") {
        global.store.emit("action-bar-count", { count: this.count, bar: this });
      }
    }

    /**
     * Static utility to update counts on arbitrary button lists matching action IDs.
     * Keeps 100% compatibility with manual DOM updates.
     */
    static syncButtonCounts(selectorOrNodeList, count, labelMap = {}) {
      const nodes = typeof selectorOrNodeList === "string"
        ? document.querySelectorAll(selectorOrNodeList)
        : selectorOrNodeList;
      if (!nodes) return;

      const suffix = count > 0 ? ` (${count})` : "";
      nodes.forEach(b => {
        const act = b.getAttribute("data-action");
        const base = (act && labelMap[act]) ? labelMap[act] : (b.getAttribute("data-base-label") || b.textContent.replace(/\s*\(\d+\)$/, ""));
        b.setAttribute("data-base-label", base);
        b.textContent = base + suffix;
      });
    }
  }

  // Export to global scope
  global.ActionBarComponent = ActionBarComponent;
})(typeof window !== "undefined" ? window : globalThis);
