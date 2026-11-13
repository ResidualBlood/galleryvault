import {
  computed,
  inject,
  isRef,
  provide,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from "vue";

/**
 * The control ladder shared by Button / IconButton / TextField / Select.
 *
 * `xl` is reserved for the single-column login / welcome forms; the three
 * working steps are `lg` (default), `md` and `sm`. Heights live in
 * `tokens.css` (`--gv-size-control-*`) so a coarse pointer can raise every
 * step by 4px without any component knowing about media queries.
 */
export type ControlSize = "xl" | "lg" | "md" | "sm";

/**
 * Legacy `size` values kept for backwards compatibility: pages still pass
 * `default` / `compact` (Button) and `default` / `small` (IconButton).
 * `compact` / `small` both resolve to `sm`; `default` resolves to the
 * inherited size (or `lg` at the top of the tree).
 */
export type LegacyControlSize = "default" | "compact" | "small";
export type ControlSizeProp = ControlSize | LegacyControlSize;

/** Injection key a Toolbar (or any container) uses to publish its step. */
export const gvControlSize: InjectionKey<ComputedRef<ControlSize>> = Symbol("gvControlSize");

/** Provide a size for every control rendered below the calling component. */
export function provideControlSize(size: ControlSize | Ref<ControlSize>): ComputedRef<ControlSize> {
  const resolved = computed(() => (isRef(size) ? size.value : size));
  provide(gvControlSize, resolved);
  return resolved;
}

/** Collapse a prop value + inherited value into one ladder step. */
export function resolveControlSize(
  explicit?: ControlSizeProp,
  inherited?: ControlSize,
): ControlSize {
  if (explicit === "compact" || explicit === "small") return "sm";
  if (explicit && explicit !== "default") return explicit;
  return inherited ?? "lg";
}

/**
 * Resolve the size for a control. An explicit prop always wins (pages that
 * mixed steps before keep working); otherwise inherit from the surrounding
 * container.
 */
export function useControlSize(explicit?: ControlSizeProp): ComputedRef<ControlSize> {
  const inherited = inject(gvControlSize, null);
  return computed(() => resolveControlSize(explicit, inherited?.value));
}

/** Icon step inside a control: 18px for the 32px control step, else 20px. */
export function controlIconSize(size: ControlSize): "dense" | "md" {
  return size === "sm" ? "dense" : "md";
}
