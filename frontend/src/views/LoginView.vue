<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Field from "@/components/ui/Field.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";
import LangToggle from "@/components/LangToggle.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const password = ref("");
const revealPassword = ref(false);
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
    <header class="login__bar" data-testid="login-bar">
      <span class="login__brand">{{ t("app.title") }}</span>
      <span class="login__spacer" />
      <div class="login__actions">
        <ThemeToggle />
        <LangToggle />
      </div>
    </header>

    <main class="login__main">
      <section class="login__card" data-testid="login-card">
        <div class="login__heading">
          <div class="login__mark" aria-hidden="true">GV</div>
          <h1 class="login__title">{{ t("login.title") }}</h1>
          <p class="login__subtitle">{{ t("login.subtitle") }}</p>
        </div>

        <form class="login__form" data-testid="login-form" @submit.prevent="submit">
          <Field :label="t('login.password')" label-for="login-password">
            <div class="login__password">
              <Input
                id="login-password"
                v-model="password"
                :type="revealPassword ? 'text' : 'password'"
                size="xl"
                autocomplete="current-password"
                :aria-label="t('login.password')"
                :error="error"
                required
              />
              <IconButton
                class="login__reveal"
                size="xl"
                name="visibility"
                :selected="revealPassword"
                :label="revealPassword ? t('login.hidePassword') : t('login.showPassword')"
                data-testid="login-reveal"
                @click="revealPassword = !revealPassword"
              />
            </div>
          </Field>
          <Button
            class="login__submit"
            type="submit"
            size="xl"
            :loading="auth.pending"
            data-testid="login-submit"
          >
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

/* Same chrome as the app shell topbar: one 56px row, one divider, blurred
   surface. LG-02: the login page used to draw a 56px bar with no border. */
.login__bar {
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  height: var(--gv-size-topbar);
  padding: 0 var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: color-mix(in srgb, var(--gv-color-surface-container) 94%, transparent);
  backdrop-filter: blur(8px);
}

.login__brand {
  flex: none;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-primary-text);
}

.login__spacer {
  flex: 1;
}

.login__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-2);
}

.login__main {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: var(--gv-space-4);
}

/* LG-04: Dialog padding is 24 (space-5), not 32. The heading group keeps a
   4px internal rhythm, then 16px between the heading and the form. */
.login__card {
  display: flex;
  width: min(420px, 100%);
  flex-direction: column;
  gap: var(--gv-space-4);
  padding: var(--gv-space-5);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-xl);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-2);
}

.login__heading {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.login__mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-space-7);
  height: var(--gv-space-7);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
  font: var(--gv-type-title-medium);
}

.login__title {
  margin: var(--gv-space-2) 0 0;
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
  gap: var(--gv-space-3);
}

.login__password {
  position: relative;
  display: flex;
  width: 100%;
  min-width: 0;
}

/* Leave room for the reveal button inside the 48px field. */
.login__password :deep(.field__control) {
  padding-right: calc(var(--gv-space-4) + var(--gv-size-control-xl));
}

.login__reveal {
  position: absolute;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
}

.login__submit {
  width: 100%;
}

.login__notice {
  margin: 0;
  padding: var(--gv-space-2) var(--gv-space-3);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
  font: var(--gv-type-body-small);
}

@media (min-width: 600px) {
  .login__bar {
    padding: 0 var(--gv-space-4);
  }
}
</style>
