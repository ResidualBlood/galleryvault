<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "card" | "list" | "line";
    lines?: number;
  }>(),
  {
    variant: "card",
    lines: 2,
  },
);
</script>

<template>
  <div class="skeleton" :class="`skeleton--${variant}`" aria-hidden="true">
    <template v-if="variant === 'line'">
      <span v-for="line in lines" :key="line" class="skeleton__line" />
    </template>
    <template v-else-if="variant === 'list'">
      <span class="skeleton__cover" />
      <span class="skeleton__lines">
        <span class="skeleton__line skeleton__line--wide" />
        <span class="skeleton__line" />
        <span class="skeleton__line skeleton__line--short" />
      </span>
    </template>
    <template v-else>
      <span class="skeleton__cover" />
      <span class="skeleton__lines">
        <span class="skeleton__line" />
        <span class="skeleton__line skeleton__line--short" />
      </span>
    </template>
  </div>
</template>

<style scoped>
.skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.skeleton--list {
  flex-direction: row;
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.skeleton__cover {
  display: block;
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  border-radius: var(--gv-radius-md);
  background: linear-gradient(
    90deg,
    var(--gv-color-surface-variant) 25%,
    var(--gv-color-surface-container-highest) 37%,
    var(--gv-color-surface-variant) 63%
  );
  background-size: 400% 100%;
  animation: skeleton-shimmer 1.2s ease-in-out infinite;
}

.skeleton--list .skeleton__cover {
  width: 104px;
  flex: 0 0 104px;
}

.skeleton__lines {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.skeleton__line {
  display: block;
  height: var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  background: linear-gradient(
    90deg,
    var(--gv-color-surface-variant) 25%,
    var(--gv-color-surface-container-highest) 37%,
    var(--gv-color-surface-variant) 63%
  );
  background-size: 400% 100%;
  animation: skeleton-shimmer 1.2s ease-in-out infinite;
}

.skeleton__line--wide {
  width: 80%;
}

.skeleton__line--short {
  width: 55%;
}

@keyframes skeleton-shimmer {
  to {
    background-position: 400% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton__cover,
  .skeleton__line {
    animation: none;
  }
}
</style>
