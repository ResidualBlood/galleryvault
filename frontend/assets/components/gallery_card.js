"use strict";

// components/gallery_card.js — GalleryVault Front-end
// Universal gallery card component for browse, favorites, and continue reading

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

  class GalleryCardComponent extends BaseComponent {
    constructor(container, props = {}) {
      super(container, props);
    }

    init() {
      this.item = this.props.item || {};
      this.mode = this.props.mode || "gallery"; // "gallery" | "fav" | "continue-reading"
      this.isSelected = !!this.props.isSelected;
    }

    /**
     * Render the component into its container.
     */
    render() {
      if (!this.container) return;
      const html = GalleryCardComponent.renderCard(this.item, {
        mode: this.mode,
        isSelected: this.isSelected,
        from: this.props.from || (typeof currentFromPath === "function" ? currentFromPath() : ""),
      });
      this.container.innerHTML = html;
      this.bindEvents();
    }

    /**
     * Bind DOM events for this card (checkbox toggle, tag click, etc.).
     */
    bindEvents() {
      if (!this.container) return;
      const checkbox = this.container.querySelector('input[type="checkbox"]');
      if (checkbox) {
        checkbox.addEventListener("change", (e) => {
          this.isSelected = e.target.checked;
          if (typeof this.props.onSelect === "function") {
            this.props.onSelect(this.item, this.isSelected, e);
          }
          if (global.store && typeof global.store.emit === "function") {
            global.store.emit("card-select", {
              item: this.item,
              selected: this.isSelected,
              mode: this.mode,
            });
          }
        });
      }
    }

    // -------------------------------------------------------------
    // Static HTML builders (100% compatible with existing markup)
    // -------------------------------------------------------------

    /**
     * Universal card renderer that dispatches by mode or item shape.
     */
    static renderCard(item, options = {}) {
      const mode = options.mode || (item.current_page != null ? "continue-reading" : (item.favcat != null || item.gid != null ? "fav" : "gallery"));
      if (mode === "continue-reading") {
        return GalleryCardComponent.renderContinueReading(item, options);
      }
      if (mode === "fav") {
        return GalleryCardComponent.renderFavCard(item, options);
      }
      return GalleryCardComponent.renderGalleryCard(item, options);
    }

    /**
     * Render a favorite gallery card (100% matching views/favorites.js favCard).
     */
    static renderFavCard(it, options = {}) {
      if (!it) return "";
      const escape = global.esc || (s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
      const translate = global.t || (k => k);
      const catLabelFn = global.catLabel || (c => c);
      const fmtSizeFn = global.fmtSize || (s => s + " B");
      const navHashFn = global.navHash || ((v, p, q) => "#/" + v);
      const currentFrom = options.from || (typeof global.currentFromPath === "function" ? global.currentFromPath() : "");
      const nsClassFn = global.nsClass || (ns => ns ? "ns-" + ns : "");
      const tagTextFn = global.tagText || (tg => (tg.namespace ? tg.namespace + ":" : "") + tg.name);

      const cat = it.category ? escape(catLabelFn(it.category)) : "";
      const cover = it.cover_url || it.cover_data || null;
      const inner = cover
        ? `<img class="cover-bg" loading="lazy" src="${cover}" alt="" aria-hidden="true"><img class="cover-fg" loading="lazy" src="${cover}" alt="">`
        : `<span class="badge">no cover</span>`;
      const stateBadge = it.gallery_id != null
        ? `<span class="fav-state local">${escape(translate("favLocal"))}</span>`
        : `<span class="fav-state cloud">${escape(translate("favCloud"))}</span>`;
      const size = it.file_size ? `<span class="gc-size">${fmtSizeFn(it.file_size)}</span>` : "";
      const link = it.gallery_id != null
        ? `href="${navHashFn("gallery", { id: it.gallery_id }, { from: currentFrom })}"`
        : `href="${escape(it.url || "#")}" target="_blank" rel="noopener"`;

      const selFavSet = global.store?.state?.selFav || global.selFav;
      const isSelected = options.isSelected != null
        ? options.isSelected
        : (selFavSet && typeof selFavSet.has === "function" ? selFavSet.has(it.gid) : false);

      const tagsHtml = (it.tags || []).map(tg => {
        const titleAttr = `${escape(tg.namespace ? tg.namespace + ":" + tg.name : tg.name)} — ${escape(translate("tagFilterHint"))} / ${escape(translate("tagExcludeHint"))}`;
        return `<span class="nst ${nsClassFn(tg.namespace)}" data-action="filter-tag" data-ns="${escape(tg.namespace)}" data-name="${escape(tg.name)}" role="button" tabindex="0" title="${titleAttr}">${escape(tagTextFn(tg))}</span>`;
      }).join("");

      return `<div class="gc-wrap">
  <a class="gc" ${link}>
    <div class="gc-cover">${inner}${stateBadge}${cat ? `<span class="gc-cat">${cat}</span>` : ""}${it.page_count ? `<span class="gc-pages">${it.page_count} P</span>` : ""}</div>
    <div class="gc-title">${escape(it.title || ("gid " + it.gid))}${size}${it.note ? `<div class="sub">${escape(it.note)}</div>` : ""}</div>
    <div class="gc-tags">${tagsHtml}</div>
  </a>
  <label class="gc-check" title="${escape(translate("select"))}"><input type="checkbox" data-fav-gid="${it.gid}"${isSelected ? " checked" : ""}></label>
</div>`;
    }

    /**
     * Render a standard library gallery card (compatible with browse/search/tag grids).
     */
    static renderGalleryCard(g, options = {}) {
      if (!g) return "";
      const escape = global.esc || (s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
      const translate = global.t || (k => k);
      const catLabelFn = global.catLabel || (c => c);
      const fmtSizeFn = global.fmtSize || (s => s + " B");
      const navHashFn = global.navHash || ((v, p, q) => "#/" + v);
      const currentFrom = options.from || (typeof global.currentFromPath === "function" ? global.currentFromPath() : "");
      const nsClassFn = global.nsClass || (ns => ns ? "ns-" + ns : "");
      const tagTextFn = global.tagText || (tg => (tg.namespace ? tg.namespace + ":" : "") + tg.name);

      const cat = g.category ? escape(catLabelFn(g.category)) : "";
      const coverSrc = g.cover_url || (g.id != null ? `/api/galleries/${g.id}/thumb/0` : null);
      const inner = coverSrc
        ? `<img class="cover-bg" loading="lazy" src="${coverSrc}" alt="" aria-hidden="true"><img class="cover-fg" loading="lazy" src="${coverSrc}" alt="${escape(g.title || "")}">`
        : `<span class="badge">no cover</span>`;

      const ratingBadge = g.rating != null && g.rating > 0
        ? `<span class="badge badge-rating">★ ${parseFloat(g.rating).toFixed(1)}</span>`
        : "";
      const pagesBadge = g.page_count ? `<span class="gc-pages">${g.page_count} P</span>` : "";
      const size = g.file_size ? `<span class="gc-size">${fmtSizeFn(g.file_size)}</span>` : "";
      const link = `href="${navHashFn("gallery", { id: g.id }, { from: currentFrom })}"`;

      const selSet = global.store?.state?.selGalleries || global.selGalleries;
      const isSelected = options.isSelected != null
        ? options.isSelected
        : (selSet && typeof selSet.has === "function" ? (selSet.has(g.id) || (g.gid && selSet.has(g.gid))) : false);

      const tagsHtml = (g.tags || []).map(tg => {
        const titleAttr = `${escape(tg.namespace ? tg.namespace + ":" + tg.name : tg.name)} — ${escape(translate("tagFilterHint"))} / ${escape(translate("tagExcludeHint"))}`;
        return `<span class="nst ${nsClassFn(tg.namespace)}" data-action="filter-tag" data-ns="${escape(tg.namespace)}" data-name="${escape(tg.name)}" role="button" tabindex="0" title="${titleAttr}">${escape(tagTextFn(tg))}</span>`;
      }).join("");

      return `<div class="gc-wrap">
  <a class="gc" ${link}>
    <div class="gc-cover">${inner}${ratingBadge}${cat ? `<span class="gc-cat">${cat}</span>` : ""}${pagesBadge}</div>
    <div class="gc-title">${escape(g.title || g.display_title || ("#" + g.id))}${size}</div>
    <div class="gc-tags">${tagsHtml}</div>
  </a>
  <label class="gc-check" title="${escape(translate("select"))}"><input type="checkbox" data-gid="${g.gid || g.id}" data-id="${g.id}"${isSelected ? " checked" : ""}></label>
</div>`;
    }

    /**
     * Render a continue reading card (100% matching views/browse.js continue reading).
     */
    static renderContinueReading(h, options = {}) {
      if (!h) return "";
      const escape = global.esc || (s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
      const translate = global.t || (k => k);
      const navHashFn = global.navHash || ((v, p, q) => "#/" + v);
      const currentFrom = options.from || (typeof global.currentFromPath === "function" ? global.currentFromPath() : "");

      const cur = h.current_page || 0;
      const total = h.total_pages || 1;
      const pct = Math.min(100, Math.round(((cur + 1) / total) * 100));
      const title = h.display_title || h.title || ("#" + h.gallery_id);
      const readUrl = navHashFn("reader", { id: h.gallery_id, page: cur }, { from: currentFrom });
      const galUrl = navHashFn("gallery", { id: h.gallery_id }, { from: currentFrom });

      return `<div class="cr-card">
  <a class="cr-thumb-wrap" href="${readUrl}">
    <img class="cover-bg" loading="lazy" src="/api/galleries/${h.gallery_id}/thumb/0" alt="" aria-hidden="true">
    <img class="cover-fg" loading="lazy" src="/api/galleries/${h.gallery_id}/thumb/0" alt="${escape(title)}">
    <div class="cr-progress-wrap">
      <div class="cr-progress-bar"><div class="cr-progress-fill" style="width:${pct}%"></div></div>
      <div class="cr-progress-text"><span>${escape(translate("progress"))} ${cur + 1}/${total}</span><span>${pct}%</span></div>
    </div>
  </a>
  <div class="cr-body">
    <a class="cr-title" href="${galUrl}" title="${escape(title)}">${escape(title)}</a>
    <div class="cr-actions">
      <a class="btn btn-secondary btn-sm" href="${readUrl}" style="padding:2px 8px;font-size:12px;">${escape(translate("readNow"))}</a>
      <button class="cr-btn-clear" data-action="clear-single-progress" data-id="${h.gallery_id}" type="button" title="${escape(translate("markUnread"))}">✕</button>
    </div>
  </div>
</div>`;
    }
  }

  // Export to global scope
  global.GalleryCardComponent = GalleryCardComponent;
})(typeof window !== "undefined" ? window : globalThis);
