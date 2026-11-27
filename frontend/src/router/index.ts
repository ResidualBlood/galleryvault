import { createRouter, createWebHashHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { routes } from "./routes";

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { left: 0, top: 0 };
  },
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.ready) await auth.init();
  if (to.meta.public) return true;
  if (!auth.authenticated) {
    return { name: "login", query: to.fullPath === "/" ? {} : { next: to.fullPath } };
  }
  return true;
});

export default router;
export { routes };
