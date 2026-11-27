<script setup lang="ts">
import { RouterView } from "vue-router";

/**
 * Pathless wrapper for the duplicate section.
 *
 * The section is nested so `/duplicates/cross-gid` keeps the `/duplicates`
 * navigation entry active (DX-05): RouterLink only treats a sibling route as
 * active when it is part of the same matched record chain. The index child
 * (`/duplicates`) renders the main view, the cross-gid child renders its own.
 */
</script>

<template>
  <RouterView />
</template>
