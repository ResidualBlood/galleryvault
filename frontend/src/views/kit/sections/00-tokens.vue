<script setup lang="ts">
/**
 * Tokens section: the control ladder and the tag namespace palette. Kept
 * dependency-free so the kit renders without any backend data.
 */
interface SizeRow {
  label: string;
  token: string;
  usage: string;
}

const sizes: SizeRow[] = [
  { label: "xl", token: "--gv-size-control-xl", usage: "login / welcome single-column forms" },
  { label: "lg", token: "--gv-size-control-lg", usage: "page toolbar, forms, dialog actions" },
  { label: "md", token: "--gv-size-control-md", usage: "inline actions, pager, settings rows" },
  { label: "sm", token: "--gv-size-control-sm", usage: "card actions, filter chips, table rows" },
];

const iconSizes: SizeRow[] = [
  { label: "sm", token: "--gv-size-icon-sm", usage: "dense inline text" },
  { label: "dense", token: "--gv-size-icon-dense", usage: "32 / 36px controls" },
  { label: "md", token: "--gv-size-icon-md", usage: "default control icon" },
  { label: "lg", token: "--gv-size-icon-lg", usage: "navigation" },
];

const namespaces = [
  "female",
  "male",
  "mixed",
  "artist",
  "group",
  "character",
  "parody",
  "language",
  "cosplayer",
  "other",
  "reclass",
  "location",
  "temp",
  "local",
  "uploader",
];
</script>

<template>
  <section class="tokens" data-testid="kit-tokens">
    <header class="tokens__header">
      <h2 class="tokens__title">Tokens</h2>
      <p class="tokens__lede">
        Control heights are one step per row; touch pointers add 4px per step without
        changing alignment.
      </p>
    </header>

    <div class="tokens__block" data-testid="kit-tokens-controls">
      <h3 class="tokens__subtitle">Control ladder</h3>
      <div class="tokens__table">
        <div class="tokens__row" v-for="size in sizes" :key="size.token" :data-token="size.token">
          <code class="tokens__label">{{ size.label }}</code>
          <div class="tokens__track">
            <span class="tokens__bar" :style="{ height: `var(${size.token})` }" />
          </div>
          <code class="tokens__name">{{ size.token }}</code>
          <span class="tokens__usage">{{ size.usage }}</span>
        </div>
      </div>
    </div>

    <div class="tokens__block" data-testid="kit-tokens-icons">
      <h3 class="tokens__subtitle">Icon sizes</h3>
      <div class="tokens__table">
        <div class="tokens__row" v-for="size in iconSizes" :key="size.token" :data-token="size.token">
          <code class="tokens__label">{{ size.label }}</code>
          <div class="tokens__track">
            <span class="tokens__icon" :style="{ width: `var(${size.token})`, height: `var(${size.token})` }" />
          </div>
          <code class="tokens__name">{{ size.token }}</code>
          <span class="tokens__usage">{{ size.usage }}</span>
        </div>
      </div>
    </div>

    <div class="tokens__block" data-testid="kit-tagns">
      <h3 class="tokens__subtitle">Tag namespaces</h3>
      <p class="tokens__lede">
        A dot carries the namespace; the chip itself shows only the tag body. Dark and light
        values are both checked against surface-container at ≥4.5:1.
      </p>
      <ul class="tokens__swatches">
        <li
          class="tokens__swatch"
          v-for="namespace in namespaces"
          :key="namespace"
          data-testid="kit-tagns-swatch"
          :data-namespace="namespace"
        >
          <span class="tokens__dot" :style="{ background: `var(--gv-tagns-${namespace})` }" />
          <code class="tokens__name">--gv-tagns-{{ namespace }}</code>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.tokens {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.tokens__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.tokens__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-large);
}

.tokens__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

.tokens__lede {
  margin: 0;
  max-width: 72ch;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.tokens__block {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.tokens__table {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.tokens__row {
  display: grid;
  grid-template-columns: 4rem 6rem minmax(0, 1fr) minmax(0, 1.2fr);
  gap: var(--gv-space-3);
  align-items: center;
  min-height: var(--gv-size-control-sm);
}

.tokens__label {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.tokens__track {
  display: flex;
  align-items: flex-end;
  height: var(--gv-size-control-xl);
}

.tokens__bar {
  display: block;
  width: 100%;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-primary-container);
}

.tokens__icon {
  display: block;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-secondary-container);
}

.tokens__name {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  overflow-wrap: anywhere;
}

.tokens__usage {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.tokens__swatches {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.tokens__swatch {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  padding: 0 var(--gv-space-2);
  min-height: var(--gv-size-tag);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
}

.tokens__dot {
  display: block;
  width: 0.5rem;
  height: 0.5rem;
  flex: none;
  border-radius: var(--gv-radius-full);
}

/* Compact: one control row per line, labels stay above the bar. */
@media (max-width: 599.98px) {
  .tokens__row {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--gv-space-1);
    padding-block: var(--gv-space-1);
  }

  .tokens__track {
    height: var(--gv-size-control-xl);
  }
}
</style>
