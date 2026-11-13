<!-- gv-polish:pending -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import LangToggle from "@/components/LangToggle.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const password = ref("");
const error = ref("");

function nextPath(): string {
  const next = route.query.next;
  return typeof next === "string" && next.startsWith("/") ? next : "/browse";
}

async function submit(): Promise<void> {
  error.value = "";
  if (!password.value) {
    error.value = t("login.error");
    return;
  }
  const ok = await auth.login(password.value);
  if (!ok) {
    error.value = t("login.error");
    password.value = "";
    return;
  }
  await router.replace(nextPath());
}

onMounted(() => {
  if (auth.authenticated) void router.replace("/browse");
});
</script>

<template>
  <div class="login">
    <header class="login__bar">
      <span class="login__brand">{{ t("app.title") }}</span>
      <span class="login__spacer" />
      <ThemeToggle />
      <LangToggle />
    </header>

    <main class="login__main">
      <section class="login__card" data-testid="login-card">
        <div class="login__mark" aria-hidden="true">GV</div>
        <h1 class="login__title">{{ t("app.title") }}</h1>
        <p class="login__subtitle">{{ t("login.subtitle") }}</p>

        <form class="login__form" data-testid="login-form" @submit.prevent="submit">
          <Input
            v-model="password"
            :label="t('login.password')"
            type="password"
            autocomplete="current-password"
            :error="error"
            required
          />
          <Button type="submit" :loading="auth.pending" data-testid="login-submit">
            {{ auth.pending ? t("login.submitting") : t("login.submit") }}
          </Button>
        </form>

        <p v-if="auth.mustChangePassword" class="login__notice">
          {{ t("login.defaultPassword") }}
        </p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  min-height: 100vh;
  flex-direction: column;
  background:
    radial-gradient(circle at 15% 0, var(--gv-color-primary-container) 0, transparent 34%),
    var(--gv-color-background);
  color: var(--gv-color-on-background);
}

.login__bar {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: var(--gv-size-topbar);
  padding: 0 var(--gv-space-4);
}

.login__brand {
  font: var(--gv-type-title-medium);
  color: var(--gv-color-primary-text);
}

.login__spacer {
  flex: 1;
}

.login__main {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: var(--gv-space-4);
}

.login__card {
  display: flex;
  width: min(420px, 100%);
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-6);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-xl);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-2);
}

.login__mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-space-7);
  height: var(--gv-space-7);
  margin-bottom: var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
  font: var(--gv-type-title-medium);
}

.login__title {
  margin: 0;
  font: var(--gv-type-headline-small);
  color: var(--gv-color-on-surface);
}

.login__subtitle {
  margin: 0;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  margin-top: var(--gv-space-4);
}

.login__notice {
  margin: var(--gv-space-2) 0 0;
  padding: var(--gv-space-2) var(--gv-space-3);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
  font: var(--gv-type-body-small);
}
</style>
