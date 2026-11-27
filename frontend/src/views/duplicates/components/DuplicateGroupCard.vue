<script setup lang="ts">
/**
 * One duplicate group: title row (gid + work title) and a metadata row
 * (chips + group action). Splitting the header into two rows means the work
 * title keeps a readable width even when the action and two chips are present
 * at 390 (DP-01). The title is single-line desktop, two-line clamp compact.
 */
withDefaults(
  defineProps<{
    title: string;
    gid?: number | null;
    testid?: string;
    muted?: boolean;
  }>(),
  { gid: null, testid: "duplicate-group", muted: false },
);
</script>

<template>
  <article
    class="dup-group"
    :class="{ 'dup-group--muted': muted }"
    :data-testid="testid"
  >
    <header class="dup-group__head">
      <div class="dup-group__title-row">
        <span v-if="gid != null" class="dup-group__gid">#{{ gid }}</span>
        <h2 class="dup-group__title" :title="title">{{ title }}</h2>
      </div>
      <div class="dup-group__meta-row">
        <div class="dup-group__badges"><slot name="badges" /></div>
        <div v-if="$slots.actions" class="dup-group__actions"><slot name="actions" /></div>
      </div>
    </header>
    <div class="dup-group__body"><slot /></div>
  </article>
</template>

<style scoped>
.dup-group {
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.dup-group--muted {
  opacity: 0.72;
}

.dup-group__head {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding-bottom: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.dup-group__title-row {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-2);
  min-width: 0;
}

.dup-group__gid {
  flex: none;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  font-variant-numeric: tabular-nums;
}

.dup-group__title {
  min-width: 160px;
  margin: 0;
  overflow: hidden;
  flex: 1 1 auto;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dup-group__meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.dup-group__badges {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.dup-group__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  margin-inline-start: auto;
}

@media (max-width: 599.98px) {
  .dup-group__title {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    white-space: normal;
  }

  .dup-group__actions {
    margin-inline-start: 0;
  }
}
</style>
