"use strict";

/**
 * base.js — 前端基础 UI 组件基类
 * 规范组件生命周期（init, render, bindEvents, destroy），
 * 提供 Store 状态自动订阅/取消订阅机制与事件委托工具，杜绝内存泄漏。
 */

(function (global) {
  class BaseComponent {
    /**
     * @param {Object} [options]
     * @param {HTMLElement|string} [options.el] 挂载的目标容器或选择器
     * @param {Object} [options.props] 外部传入的组件属性
     * @param {Store} [options.store] 绑定的状态机实例，默认为全局 store
     * @param {boolean} [options.autoRender=true] 是否在构造时自动调用 render
     */
    constructor(options = {}) {
      this.options = Object.assign({}, options);
      this.props = Object.assign({}, options.props || {});
      this.store = options.store || (typeof window !== "undefined" ? window.store : null);
      this.state = {};

      this._unsubscribers = [];
      this._domListeners = [];
      this._isDestroyed = false;

      // 解析根元素
      if (typeof options.el === "string") {
        this.$el = document.querySelector(options.el);
      } else if (options.el instanceof HTMLElement) {
        this.$el = options.el;
      } else {
        this.$el = null;
      }

      // 执行生命周期初始化钩子
      this.init();

      // 若已指定容器且未禁用 autoRender，自动渲染并绑定事件
      if (this.$el && options.autoRender !== false) {
        this.render();
        this.bindEvents();
      }
    }

    /**
     * 初始化钩子，子类重写用于初始化局部 state 或订阅 Store
     */
    init() {}

    /**
     * 渲染视图，子类重写实现具体 DOM 生成或更新
     * @returns {BaseComponent|HTMLElement}
     */
    render() {
      return this;
    }

    /**
     * 事件绑定钩子，子类重写用于注册交互事件
     */
    bindEvents() {}

    /**
     * 更新组件内部局部状态
     * @param {Object} partialState
     * @param {Object} [opts]
     * @param {boolean} [opts.render=true] 是否在状态更新后触发重新渲染
     */
    setState(partialState, opts = {}) {
      if (this._isDestroyed) return;
      const shouldRender = opts.render !== false;
      this.state = Object.assign({}, this.state, partialState);
      if (shouldRender) {
        this.render();
      }
    }

    /**
     * 更新传入的 props
     * @param {Object} partialProps
     * @param {Object} [opts]
     * @param {boolean} [opts.render=true]
     */
    setProps(partialProps, opts = {}) {
      if (this._isDestroyed) return;
      const shouldRender = opts.render !== false;
      this.props = Object.assign({}, this.props, partialProps);
      if (shouldRender) {
        this.render();
      }
    }

    /**
     * 订阅 Store 状态变更，自动在组件销毁时取消订阅
     * @param {string|Function} keyOrListener
     * @param {Function} [maybeListener]
     * @returns {Function} 取消订阅函数
     */
    subscribeStore(keyOrListener, maybeListener) {
      if (!this.store || typeof this.store.subscribe !== "function") {
        console.warn("[BaseComponent] store is not available for subscription");
        return () => {};
      }

      const unsubscribe = this.store.subscribe(keyOrListener, maybeListener);
      this._unsubscribers.push(unsubscribe);
      return unsubscribe;
    }

    /**
     * DOM 事件监听与委托辅助函数。
     * 支持:
     * 1. this.on('click', '.btn', handler) -> 委托监听
     * 2. this.on('click', handler) -> 直接监听根元素
     * 自动在 destroy 时统一注销。
     *
     * @param {string} eventName
     * @param {string|Function} selectorOrHandler
     * @param {Function} [maybeHandler]
     */
    on(eventName, selectorOrHandler, maybeHandler) {
      if (!this.$el) return;

      const isDelegated = typeof selectorOrHandler === "string" && typeof maybeHandler === "function";
      const selector = isDelegated ? selectorOrHandler : null;
      const handler = isDelegated ? maybeHandler : selectorOrHandler;

      if (typeof handler !== "function") return;

      const listener = (event) => {
        if (isDelegated) {
          const target = event.target && event.target.closest(selector);
          if (target && this.$el.contains(target)) {
            handler.call(this, event, target);
          }
        } else {
          handler.call(this, event);
        }
      };

      this.$el.addEventListener(eventName, listener);
      this._domListeners.push({
        el: this.$el,
        eventName,
        listener,
      });

      return () => {
        if (this.$el) {
          this.$el.removeEventListener(eventName, listener);
        }
      };
    }

    /**
     * 在根元素或全局派发自定义事件
     * @param {string} eventName
     * @param {*} [detail]
     * @param {Object} [options]
     */
    emit(eventName, detail, options = {}) {
      const event = new CustomEvent(eventName, {
        bubbles: true,
        cancelable: true,
        detail,
        ...options,
      });
      if (this.$el) {
        this.$el.dispatchEvent(event);
      }
      return event;
    }

    /**
     * 快捷子元素查找
     */
    $(selector) {
      return this.$el ? this.$el.querySelector(selector) : null;
    }

    $$(selector) {
      return this.$el ? Array.from(this.$el.querySelectorAll(selector)) : [];
    }

    /**
     * 销毁组件生命周期：清理 Store 订阅与 DOM 监听
     * @param {boolean} [removeElement=false] 是否连同根元素一并从 DOM 移除
     */
    destroy(removeElement = false) {
      if (this._isDestroyed) return;
      this._isDestroyed = true;

      // 1. 取消所有 Store 订阅
      while (this._unsubscribers.length > 0) {
        const unsub = this._unsubscribers.pop();
        try {
          unsub();
        } catch (err) {
          console.error("[BaseComponent] error during unsubscribe:", err);
        }
      }

      // 2. 解绑所有 DOM 事件
      while (this._domListeners.length > 0) {
        const { el, eventName, listener } = this._domListeners.pop();
        try {
          if (el) el.removeEventListener(eventName, listener);
        } catch (err) {
          console.error("[BaseComponent] error removing DOM listener:", err);
        }
      }

      // 3. 移除 DOM 元素或清空内容
      if (this.$el) {
        if (removeElement && this.$el.parentNode) {
          this.$el.parentNode.removeChild(this.$el);
        }
      }

      this.emit("destroy");
    }
  }

  global.BaseComponent = BaseComponent;
})(typeof window !== "undefined" ? window : globalThis);
