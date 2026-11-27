/**
 * Minimal jsdom shims for APIs the components use but jsdom does not implement.
 *
 * jsdom ships `HTMLDialogElement` without `showModal`/`close`, so component
 * tests would crash instead of exercising the real code path. The shim mirrors
 * the observable DOM contract: `showModal()`/`show()` set the `open` attribute,
 * `close()` clears it and dispatches a `close` event.
 */
const dialogProto = window.HTMLDialogElement?.prototype;

if (dialogProto) {
  if (!dialogProto.showModal) {
    dialogProto.showModal = function showModal(this: HTMLDialogElement): void {
      this.open = true;
    };
  }
  if (!dialogProto.show) {
    dialogProto.show = function show(this: HTMLDialogElement): void {
      this.open = true;
    };
  }
  if (!dialogProto.close) {
    dialogProto.close = function close(this: HTMLDialogElement, returnValue?: string): void {
      if (returnValue !== undefined) this.returnValue = returnValue;
      if (!this.open) return;
      this.open = false;
      this.dispatchEvent(new Event("close"));
    };
  }
  if (!dialogProto.requestClose) {
    dialogProto.requestClose = function requestClose(this: HTMLDialogElement): void {
      const event = new Event("cancel", { cancelable: true });
      if (this.dispatchEvent(event)) this.close();
    };
  }
}
