"use strict";

/**
 * store.js — 轻量级响应式单向数据流 Store 与全局事件中心
 * 基于浏览器原生 EventTarget，提供集中状态托管、单向 Action 分发与细粒度变更订阅。
 */

(function (global) {
  class Store extends EventTarget {
    constructor(initialState = {}) {
      super();
      this._state = Object.assign({}, initialState);
      this._actionHandlers = new Map();
      this._proxy = null;
    }

    /**
     * 响应式 Proxy 代理，支持 store.state.key 读写并自动触发事件
     */
    get state() {
      if (!this._proxy) {
        this._proxy = new Proxy(this._state, {
          get: (target, prop) => {
            if (typeof prop === "symbol") return target[prop];
            return target[prop];
          },
          set: (target, prop, value) => {
            if (typeof prop === "symbol") {
              target[prop] = value;
              return true;
            }
            this.setState(prop, value);
            return true;
          },
        });
      }
      return this._proxy;
    }

    /**
     * 获取状态值。传 key 返回对应字段，无参数返回整体状态快照。
     * @param {string} [key]
     * @returns {*}
     */
    getState(key) {
      if (typeof key === "string") {
        return this._state[key];
      }
      return Object.assign({}, this._state);
    }

    /**
     * 更新状态。
     * 支持:
     * 1. setState('key', value, options)
     * 2. setState({ key1: val1, key2: val2 }, options)
     *
     * @param {string|Object} partialStateOrKey
     * @param {*} [value]
     * @param {Object} [options]
     */
    setState(partialStateOrKey, value, options = {}) {
      const isSingleKey = typeof partialStateOrKey === "string";
      const updates = isSingleKey ? { [partialStateOrKey]: value } : (partialStateOrKey || {});
      const opts = isSingleKey
        ? (typeof options === "object" && options !== null ? options : {})
        : (typeof value === "object" && value !== null ? value : {});

      const silent = Boolean(opts.silent);
      const action = opts.action || null;

      const changedKeys = [];
      const prevValues = {};

      for (const k of Object.keys(updates)) {
        const oldVal = this._state[k];
        const newVal = updates[k];
        if (oldVal !== newVal) {
          prevValues[k] = oldVal;
          this._state[k] = newVal;
          changedKeys.push(k);
        }
      }

      if (changedKeys.length === 0) return;

      if (!silent) {
        // 1. 触发细粒度单个 key 的变更事件
        for (const k of changedKeys) {
          const detail = {
            key: k,
            value: this._state[k],
            oldValue: prevValues[k],
            action,
          };
          this.dispatchEvent(new CustomEvent(`change:${k}`, { detail }));
        }

        // 2. 触发整体变更事件
        const summaryDetail = {
          changedKeys,
          prevValues,
          state: this.getState(),
          action,
        };
        this.dispatchEvent(new CustomEvent("change", { detail: summaryDetail }));
      }
    }

    /**
     * 订阅状态变更。
     * 支持:
     * 1. subscribe('key', (detail) => {})
     * 2. subscribe((detail) => {})
     *
     * @param {string|Function} keyOrListener
     * @param {Function} [maybeListener]
     * @returns {Function} 取消订阅函数
     */
    subscribe(keyOrListener, maybeListener) {
      let eventName = "change";
      let listener = maybeListener;

      if (typeof keyOrListener === "function") {
        eventName = "change";
        listener = keyOrListener;
      } else if (typeof keyOrListener === "string" && typeof maybeListener === "function") {
        eventName = `change:${keyOrListener}`;
        listener = maybeListener;
      } else {
        throw new TypeError("Store.subscribe: invalid arguments");
      }

      const wrapped = (e) => {
        try {
          listener(e.detail, e);
        } catch (err) {
          console.error(`[Store] error in subscription listener for ${eventName}:`, err);
        }
      };

      this.addEventListener(eventName, wrapped);
      return () => {
        this.removeEventListener(eventName, wrapped);
      };
    }

    /**
     * 注册 Action 处理函数
     * @param {string} type
     * @param {Function} handler (context, payload) => any
     */
    registerAction(type, handler) {
      if (typeof type !== "string" || typeof handler !== "function") {
        throw new TypeError("Store.registerAction: type must be string and handler must be function");
      }
      this._actionHandlers.set(type, handler);
    }

    /**
     * 单向数据流 Action 分发器
     * @param {string|Object} action
     * @param {*} [payload]
     * @returns {Promise<*>}
     */
    async dispatch(action, payload) {
      const actionType = typeof action === "string" ? action : (action && action.type);
      const actionPayload = typeof action === "string" ? payload : (action && action.payload);

      if (!actionType) {
        throw new Error("Store.dispatch: action must have a type");
      }

      this.dispatchEvent(new CustomEvent(`action:${actionType}`, {
        detail: { action: actionType, payload: actionPayload },
      }));
      this.dispatchEvent(new CustomEvent("action", {
        detail: { action: actionType, payload: actionPayload },
      }));

      const handler = this._actionHandlers.get(actionType);
      if (handler) {
        const context = {
          state: this.getState(),
          getState: (k) => this.getState(k),
          setState: (k, v, o) => this.setState(k, v, Object.assign({ action: actionType }, o)),
          dispatch: (a, p) => this.dispatch(a, p),
        };
        return await handler(context, actionPayload);
      }
      return null;
    }

    /**
     * 通用事件监听与总线接口
     */
    on(event, handler) {
      this.addEventListener(event, handler);
      return () => this.removeEventListener(event, handler);
    }

    off(event, handler) {
      this.removeEventListener(event, handler);
    }

    emit(event, detail) {
      this.dispatchEvent(new CustomEvent(event, { detail }));
    }
  }

  // 挂载全局单例
  const store = new Store();
  global.Store = Store;
  global.store = store;
})(typeof window !== "undefined" ? window : globalThis);
