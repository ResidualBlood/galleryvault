"use strict";

/**
 * pagination.js — 通用分页控制器 UI 组件
 * 继承 BaseComponent，统一渲染页码、跳转、每页条数选择并触发统一翻页事件。
 */

(function (global) {
  const BaseComponent = global.BaseComponent;
  if (!BaseComponent) {
    throw new Error("PaginationComponent requires BaseComponent to be loaded first.");
  }

  const DEFAULT_PAGE_SIZES = [5, 30, 50, 100, 200, 500];

  class PaginationComponent extends BaseComponent {
    init() {
      // 规范化 Props 默认值
      this.props = {
        page: 1,
        pageSize: 50,
        total: 0,
        pageSizes: DEFAULT_PAGE_SIZES,
        showPageSizes: true,
        showJump: true,
        showTotal: true,
        maxVisibleButtons: 7,
        onPageChange: null,
        onPageSizeChange: null,
        ...this.props,
      };

      // 确保数值类型合法
      this.props.page = Math.max(1, parseInt(this.props.page, 10) || 1);
      this.props.pageSize = Math.max(1, parseInt(this.props.pageSize, 10) || 50);
      this.props.total = Math.max(0, parseInt(this.props.total, 10) || 0);

      // 若未指定挂载根节点，自动创建默认容器
      if (!this.$el) {
        this.$el = document.createElement("div");
        this.$el.className = "pagination-component-container";
      }
    }

    get totalPages() {
      const { total, pageSize } = this.props;
      return Math.max(1, Math.ceil(total / pageSize));
    }

    get currentPage() {
      return Math.min(Math.max(1, this.props.page), this.totalPages);
    }

    /**
     * 计算中间按钮显示的页码序列，包含数字和省略号 "..."
     * @returns {Array<number|string>}
     */
    _calculateVisiblePages() {
      const totalPages = this.totalPages;
      const current = this.currentPage;
      const maxButtons = this.props.maxVisibleButtons || 7;

      if (totalPages <= maxButtons) {
        const pages = [];
        for (let i = 1; i <= totalPages; i++) pages.push(i);
        return pages;
      }

      const pages = [1];
      const sideButtons = Math.floor((maxButtons - 4) / 2); // 留出 1, 尾页, 两个省略号的位置
      let left = Math.max(2, current - sideButtons);
      let right = Math.min(totalPages - 1, current + sideButtons);

      if (current - 1 <= sideButtons + 1) {
        right = Math.min(totalPages - 1, 1 + (maxButtons - 3));
      } else if (totalPages - current <= sideButtons + 1) {
        left = Math.max(2, totalPages - (maxButtons - 3));
      }

      if (left > 2) {
        pages.push("...");
      }

      for (let i = left; i <= right; i++) {
        pages.push(i);
      }

      if (right < totalPages - 1) {
        pages.push("...");
      }

      pages.push(totalPages);
      return pages;
    }

    /**
     * 渲染完整分页 HTML 结构
     */
    render() {
      if (!this.$el) return this;

      const { total, pageSize, showPageSizes, showJump, showTotal, pageSizes } = this.props;
      const totalPages = this.totalPages;
      const current = this.currentPage;
      const visiblePages = this._calculateVisiblePages();

      // 构建每页条数选择框
      let sizeSelectHtml = "";
      if (showPageSizes && Array.isArray(pageSizes) && pageSizes.length > 0) {
        const optionsHtml = pageSizes
          .map((size) => `<option value="${size}" ${size === pageSize ? "selected" : ""}>${size} / 页</option>`)
          .join("");
        sizeSelectHtml = `
          <div class="pagination-sizes">
            <select class="form-select form-select-sm pagination-size-select" aria-label="每页条数">
              ${optionsHtml}
            </select>
          </div>
        `;
      }

      // 构建快捷跳转框
      let jumpHtml = "";
      if (showJump && totalPages > 1) {
        jumpHtml = `
          <div class="pagination-jump">
            <input type="number" min="1" max="${totalPages}" class="form-control form-control-sm pagination-jump-input" placeholder="${current}" aria-label="跳转页码" />
            <button type="button" class="btn btn-sm btn-outline-secondary pagination-jump-btn">跳转</button>
          </div>
        `;
      }

      // 构建总计信息
      let totalHtml = "";
      if (showTotal) {
        totalHtml = `
          <span class="pagination-info text-muted small">
            第 <strong class="pagination-current-page">${current}</strong> / <strong class="pagination-total-pages">${totalPages}</strong> 页
            (共 <strong class="pagination-total-items">${total}</strong> 项)
          </span>
        `;
      }

      // 构建页码按钮组
      let pageButtonsHtml = "";
      if (totalPages > 1 || total > 0) {
        const prevDisabled = current <= 1 ? "disabled" : "";
        const nextDisabled = current >= totalPages ? "disabled" : "";

        const itemsHtml = visiblePages
          .map((item) => {
            if (item === "...") {
              return '<span class="pagination-ellipsis px-2 py-1 text-muted">…</span>';
            }
            const isActive = item === current;
            return `
              <button type="button"
                class="btn btn-sm ${isActive ? "btn-primary active font-weight-bold" : "btn-outline-secondary"} pagination-page-btn"
                data-page="${item}"
                ${isActive ? 'aria-current="page"' : ""}>
                ${item}
              </button>
            `;
          })
          .join("");

        pageButtonsHtml = `
          <div class="pagination-nav-group btn-group btn-group-sm" role="group" aria-label="分页导航">
            <button type="button" class="btn btn-outline-secondary pagination-page-btn" data-page="1" title="首页" ${prevDisabled}>«</button>
            <button type="button" class="btn btn-outline-secondary pagination-page-btn" data-page="${current - 1}" title="上一页" ${prevDisabled}>‹</button>
            ${itemsHtml}
            <button type="button" class="btn btn-outline-secondary pagination-page-btn" data-page="${current + 1}" title="下一页" ${nextDisabled}>›</button>
            <button type="button" class="btn btn-outline-secondary pagination-page-btn" data-page="${totalPages}" title="尾页" ${nextDisabled}>»</button>
          </div>
        `;
      }

      this.$el.innerHTML = `
        <div class="pagination-component d-flex flex-wrap align-items-center justify-content-between gap-2 py-2">
          <div class="pagination-left d-flex align-items-center gap-2">
            ${totalHtml}
            ${sizeSelectHtml}
          </div>
          <div class="pagination-right d-flex align-items-center gap-2">
            ${pageButtonsHtml}
            ${jumpHtml}
          </div>
        </div>
      `;

      return this;
    }

    /**
     * 绑定 DOM 交互事件
     */
    bindEvents() {
      // 1. 点击页码按钮
      this.on("click", ".pagination-page-btn", (e, target) => {
        e.preventDefault();
        if (target.hasAttribute("disabled") || target.classList.contains("disabled")) return;
        const targetPage = parseInt(target.getAttribute("data-page"), 10);
        if (!isNaN(targetPage)) {
          this.goToPage(targetPage);
        }
      });

      // 2. 切换每页条数
      this.on("change", ".pagination-size-select", (e, target) => {
        const newSize = parseInt(target.value, 10);
        if (!isNaN(newSize) && newSize > 0) {
          this.changePageSize(newSize);
        }
      });

      // 3. 快捷跳转
      this.on("click", ".pagination-jump-btn", (e) => {
        e.preventDefault();
        this._handleJump();
      });

      this.on("keydown", ".pagination-jump-input", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          this._handleJump();
        }
      });
    }

    _handleJump() {
      const input = this.$(".pagination-jump-input");
      if (!input) return;
      const val = parseInt(input.value, 10);
      if (isNaN(val) || val < 1 || val > this.totalPages) {
        input.classList.add("is-invalid");
        return;
      }
      input.classList.remove("is-invalid");
      this.goToPage(val);
    }

    /**
     * 切换到目标页码
     * @param {number} newPage
     */
    goToPage(newPage) {
      const validPage = Math.min(Math.max(1, newPage), this.totalPages);
      if (validPage === this.currentPage && this.props.page === validPage) {
        return;
      }

      this.props.page = validPage;
      this.render();

      // 触发回调与 DOM 事件
      if (typeof this.props.onPageChange === "function") {
        try {
          this.props.onPageChange(validPage, this.props.pageSize);
        } catch (err) {
          console.error("[PaginationComponent] onPageChange error:", err);
        }
      }

      this.emit("page-change", {
        page: validPage,
        pageSize: this.props.pageSize,
        total: this.props.total,
        totalPages: this.totalPages,
      });
    }

    /**
     * 切换每页显示条数
     * @param {number} newSize
     */
    changePageSize(newSize) {
      if (newSize === this.props.pageSize) return;

      this.props.pageSize = newSize;
      this.props.page = 1; // 切换条数后重置回第 1 页
      this.render();

      if (typeof this.props.onPageSizeChange === "function") {
        try {
          this.props.onPageSizeChange(newSize);
        } catch (err) {
          console.error("[PaginationComponent] onPageSizeChange error:", err);
        }
      }

      if (typeof this.props.onPageChange === "function") {
        try {
          this.props.onPageChange(1, newSize);
        } catch (err) {
          console.error("[PaginationComponent] onPageChange error:", err);
        }
      }

      this.emit("pagesize-change", { pageSize: newSize });
      this.emit("page-change", {
        page: 1,
        pageSize: newSize,
        total: this.props.total,
        totalPages: this.totalPages,
      });
    }

    /**
     * 便捷更新分页状态
     * @param {Object} data
     * @param {number} [data.page]
     * @param {number} [data.pageSize]
     * @param {number} [data.total]
     */
    update(data = {}) {
      let changed = false;

      if (data.total !== undefined) {
        const total = Math.max(0, parseInt(data.total, 10) || 0);
        if (total !== this.props.total) {
          this.props.total = total;
          changed = true;
        }
      }

      if (data.pageSize !== undefined) {
        const pageSize = Math.max(1, parseInt(data.pageSize, 10) || 50);
        if (pageSize !== this.props.pageSize) {
          this.props.pageSize = pageSize;
          changed = true;
        }
      }

      if (data.page !== undefined) {
        const page = Math.max(1, parseInt(data.page, 10) || 1);
        if (page !== this.props.page) {
          this.props.page = page;
          changed = true;
        }
      }

      if (changed) {
        this.render();
      }
    }
  }

  global.PaginationComponent = PaginationComponent;
})(typeof window !== "undefined" ? window : globalThis);
