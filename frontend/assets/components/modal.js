"use strict";

// components/modal.js — GalleryVault Front-end
// Universal modal/dialog component with overlay, transitions, and keyboard lifecycle

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

  // Stack of active modals to handle Escape key hierarchy
  const activeModalStack = [];

  function onGlobalKeyDown(e) {
    if (e.key === "Escape" && activeModalStack.length > 0) {
      const topModal = activeModalStack[activeModalStack.length - 1];
      if (topModal && topModal.props.closeOnEsc !== false) {
        e.preventDefault();
        topModal.close(null);
      }
    }
  }

  if (typeof document !== "undefined") {
    document.addEventListener("keydown", onGlobalKeyDown);
  }

  class ModalComponent extends BaseComponent {
    constructor(props = {}) {
      // Container defaults to document.body for top-level overlay modals
      const container = props.container || (typeof document !== "undefined" ? document.body : null);
      super(container, props);
    }

    init() {
      this.title = this.props.title || "";
      this.body = this.props.body || "";
      this.footer = this.props.footer || "";
      this.buttons = this.props.buttons || null;
      this.closeOnClickBackdrop = this.props.closeOnClickBackdrop !== false;
      this.closeOnEsc = this.props.closeOnEsc !== false;
      this.isOpen = false;
      this.overlayEl = null;
      this._resolvePromise = null;
    }

    /**
     * Build modal DOM elements.
     */
    buildElement() {
      const escape = global.esc || (s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
      const translate = global.t || (k => k);

      const overlay = document.createElement("div");
      overlay.className = "modal-backdrop" + (this.props.className ? " " + this.props.className : "");
      overlay.setAttribute("role", "presentation");
      overlay.style.position = "fixed";
      overlay.style.inset = "0";
      overlay.style.backgroundColor = "rgba(0, 0, 0, 0.65)";
      overlay.style.display = "flex";
      overlay.style.alignItems = "center";
      overlay.style.justifyContent = "center";
      overlay.style.zIndex = String(10000 + activeModalStack.length * 10);
      overlay.style.opacity = "0";
      overlay.style.transition = "opacity 0.2s ease-in-out";

      const dialog = document.createElement("div");
      dialog.className = "modal-dialog modal-card";
      dialog.setAttribute("role", "dialog");
      dialog.setAttribute("aria-modal", "true");
      dialog.style.maxWidth = this.props.maxWidth || "540px";
      dialog.style.width = "90%";
      dialog.style.maxHeight = "90vh";
      dialog.style.overflowY = "auto";
      dialog.style.backgroundColor = "var(--bg-card, #1e1e24)";
      dialog.style.color = "var(--text-main, #f0f0f0)";
      dialog.style.borderRadius = "8px";
      dialog.style.boxShadow = "0 12px 32px rgba(0, 0, 0, 0.4)";
      dialog.style.padding = "20px";
      dialog.style.transform = "scale(0.95)";
      dialog.style.transition = "transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)";

      // Header
      const header = document.createElement("div");
      header.className = "modal-header";
      header.style.display = "flex";
      header.style.justifyContent = "space-between";
      header.style.alignItems = "center";
      header.style.marginBottom = "16px";

      const titleEl = document.createElement("h3");
      titleEl.className = "modal-title";
      titleEl.style.margin = "0";
      titleEl.style.fontSize = "18px";
      titleEl.style.fontWeight = "600";
      titleEl.innerHTML = typeof this.title === "string" ? escape(this.title) : "";
      if (this.title instanceof Node) titleEl.appendChild(this.title);

      const closeBtn = document.createElement("button");
      closeBtn.className = "modal-close btn-clear";
      closeBtn.setAttribute("type", "button");
      closeBtn.setAttribute("aria-label", "Close");
      closeBtn.style.background = "none";
      closeBtn.style.border = "none";
      closeBtn.style.color = "inherit";
      closeBtn.style.fontSize = "20px";
      closeBtn.style.cursor = "pointer";
      closeBtn.style.lineHeight = "1";
      closeBtn.style.padding = "4px 8px";
      closeBtn.innerHTML = "✕";
      closeBtn.addEventListener("click", () => this.close(null));

      header.appendChild(titleEl);
      header.appendChild(closeBtn);
      dialog.appendChild(header);

      // Body
      const bodyEl = document.createElement("div");
      bodyEl.className = "modal-body";
      bodyEl.style.marginBottom = "20px";
      bodyEl.style.lineHeight = "1.5";
      if (typeof this.body === "string") {
        bodyEl.innerHTML = this.body;
      } else if (this.body instanceof Node) {
        bodyEl.appendChild(this.body);
      }
      dialog.appendChild(bodyEl);

      // Footer
      const footerEl = document.createElement("div");
      footerEl.className = "modal-footer";
      footerEl.style.display = "flex";
      footerEl.style.justifyContent = "flex-end";
      footerEl.style.gap = "8px";

      if (Array.isArray(this.buttons)) {
        this.buttons.forEach(btnConfig => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn " + (btnConfig.primary ? "btn-primary" : "btn-secondary") + (btnConfig.danger ? " danger" : "") + (btnConfig.className ? " " + btnConfig.className : "");
          btn.textContent = btnConfig.text || btnConfig.label || "";
          btn.addEventListener("click", async (e) => {
            if (typeof btnConfig.onClick === "function") {
              const res = await btnConfig.onClick(this, e);
              if (res !== false) this.close(btnConfig.value !== undefined ? btnConfig.value : true);
            } else {
              this.close(btnConfig.value !== undefined ? btnConfig.value : true);
            }
          });
          footerEl.appendChild(btn);
        });
        dialog.appendChild(footerEl);
      } else if (typeof this.footer === "string" && this.footer) {
        footerEl.innerHTML = this.footer;
        dialog.appendChild(footerEl);
      } else if (this.footer instanceof Node) {
        footerEl.appendChild(this.footer);
        dialog.appendChild(footerEl);
      }

      overlay.appendChild(dialog);

      // Click on backdrop to close
      overlay.addEventListener("click", (e) => {
        if (this.closeOnClickBackdrop && e.target === overlay) {
          this.close(null);
        }
      });

      return overlay;
    }

    /**
     * Open modal dialog and display with animation.
     * Returns a Promise resolving to user action/result.
     */
    open() {
      return new Promise((resolve) => {
        this._resolvePromise = resolve;
        if (this.isOpen) return;

        this.overlayEl = this.buildElement();
        const target = this.container || document.body;
        target.appendChild(this.overlayEl);
        this.isOpen = true;
        activeModalStack.push(this);

        // Trigger animation on next frame
        requestAnimationFrame(() => {
          if (!this.overlayEl) return;
          this.overlayEl.style.opacity = "1";
          const dlg = this.overlayEl.querySelector(".modal-dialog");
          if (dlg) dlg.style.transform = "scale(1)";
        });

        if (typeof this.props.onOpen === "function") {
          this.props.onOpen(this);
        }
        if (global.store && typeof global.store.emit === "function") {
          global.store.emit("modal-open", { modal: this });
        }
      });
    }

    /**
     * Close modal dialog with optional exit value.
     */
    close(result) {
      if (!this.isOpen || !this.overlayEl) {
        if (this._resolvePromise) this._resolvePromise(result);
        return;
      }

      if (typeof this.props.beforeClose === "function") {
        if (this.props.beforeClose(result) === false) return;
      }

      const idx = activeModalStack.indexOf(this);
      if (idx !== -1) activeModalStack.splice(idx, 1);

      this.overlayEl.style.opacity = "0";
      const dlg = this.overlayEl.querySelector(".modal-dialog");
      if (dlg) dlg.style.transform = "scale(0.95)";

      setTimeout(() => {
        if (this.overlayEl && this.overlayEl.parentNode) {
          this.overlayEl.parentNode.removeChild(this.overlayEl);
        }
        this.overlayEl = null;
        this.isOpen = false;

        if (typeof this.props.onClose === "function") {
          this.props.onClose(result);
        }
        if (global.store && typeof global.store.emit === "function") {
          global.store.emit("modal-close", { modal: this, result });
        }
        if (this._resolvePromise) {
          this._resolvePromise(result);
          this._resolvePromise = null;
        }
      }, 200);
    }

    /**
     * Lifecycle destroy cleanup.
     */
    destroy() {
      this.close(null);
      super.destroy();
    }

    // -------------------------------------------------------------
    // Static Helpers
    // -------------------------------------------------------------

    /**
     * Show a custom modal immediately and return its instance.
     */
    static show(options = {}) {
      const modal = new ModalComponent(options);
      modal.open();
      return modal;
    }

    /**
     * Display a standard Confirm modal and return a Promise<boolean>.
     */
    static confirm(message, title) {
      const translate = global.t || (k => k);
      return new Promise((resolve) => {
        const modal = new ModalComponent({
          title: title || translate("confirm") || "Confirm",
          body: `<p style="margin:0">${typeof message === "string" ? message : ""}</p>`,
          buttons: [
            { text: translate("cancel") || "Cancel", primary: false, value: false },
            { text: translate("ok") || "OK", primary: true, value: true },
          ],
        });
        modal.open().then(val => resolve(!!val));
      });
    }

    /**
     * Display an Alert modal and return a Promise<void>.
     */
    static alert(message, title) {
      const translate = global.t || (k => k);
      return new Promise((resolve) => {
        const modal = new ModalComponent({
          title: title || translate("notice") || "Notice",
          body: `<p style="margin:0">${typeof message === "string" ? message : ""}</p>`,
          buttons: [
            { text: translate("ok") || "OK", primary: true, value: true },
          ],
        });
        modal.open().then(() => resolve());
      });
    }
  }

  // Export to global scope
  global.ModalComponent = ModalComponent;
})(typeof window !== "undefined" ? window : globalThis);
