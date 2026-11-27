import { ref } from "vue";
import { request, type Endpoint, type RequestOptions } from "@/api/client";

export interface ViewRequestContext {
  token: number;
  signal: AbortSignal;
  stale: (view?: string, id?: string) => boolean;
  abort: () => void;
  api: <T = unknown>(endpoint: Endpoint, options?: Omit<RequestOptions, "signal">) => Promise<T>;
}

/**
 * Port of the legacy view-runtime contract (inv-frontend.md §2.2):
 * every render gets a monotonically increasing token plus an AbortController;
 * responses whose token or route is stale are ignored by callers.
 */
export function useViewRequest() {
  let seq = 0;
  let controller: AbortController | null = null;
  const view = ref("");
  const id = ref("");

  function begin(nextView = "", nextId = ""): ViewRequestContext {
    seq += 1;
    controller?.abort();
    controller = new AbortController();
    view.value = nextView;
    id.value = nextId;
    const token = seq;
    const signal = controller.signal;
    const stale = (expectedView?: string, expectedId?: string): boolean => {
      if (token !== seq) return true;
      if (expectedView !== undefined && expectedView !== view.value) return true;
      if (expectedId !== undefined && expectedId !== id.value) return true;
      return false;
    };
    return {
      token,
      signal,
      stale,
      abort: () => controller?.abort(),
      api: <T = unknown>(
        endpoint: Endpoint,
        options: Omit<RequestOptions, "signal"> = {},
      ) => request<T>(endpoint, { ...options, signal }),
    };
  }

  function abort(): void {
    seq += 1;
    controller?.abort();
  }

  async function withViewRequest<T>(
    nextView: string,
    nextId: string,
    run: (context: ViewRequestContext) => Promise<T>,
  ): Promise<T | undefined> {
    const context = begin(nextView, nextId);
    try {
      return await run(context);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return undefined;
      if (context.stale()) return undefined;
      throw error;
    }
  }

  return { begin, abort, withViewRequest, view, id };
}
