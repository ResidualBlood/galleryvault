import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";
import tseslint from "typescript-eslint";

const BARE_API_RULE = [
  "error",
  {
    selector: "Literal[value=/^\\/api\\//]",
    message:
      "Declare API endpoints in src/api/<domain>.ts with ep('METHOD', '/api/...') instead of a bare string.",
  },
  {
    selector: "TemplateElement[value.raw=/^\\/api\\//]",
    message:
      "Declare API endpoints in src/api/<domain>.ts with ep('METHOD', '/api/...') instead of a bare template.",
  },
];

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "scripts/check-design.mjs",
      "playwright-report/**",
      "test-results/**",
      "blob-report/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/essential"],
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    rules: {
      "vue/multi-word-component-names": "off",
    },
  },
  {
    files: ["**/*.ts", "**/*.vue"],
    languageOptions: {
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      "no-restricted-syntax": BARE_API_RULE,
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    files: ["src/api/**/*.ts"],
    rules: {
      "no-restricted-syntax": "off",
    },
  },
  {
    files: [
      "*.config.ts",
      "scripts/**/*.mjs",
      "eslint.config.js",
      "vite.config.ts",
      "vitest.config.ts",
      "playwright*.config.ts",
    ],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
  {
    files: ["e2e/**/*.ts"],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.browser,
      },
    },
  },
);
