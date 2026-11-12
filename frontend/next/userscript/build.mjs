#!/usr/bin/env node
/* global Buffer, console, process */
/**
 * Build `public/galleryvault-companion.user.js` from `userscript/companion.mjs`.
 *
 *   node userscript/build.mjs           # write the userscript
 *   node userscript/build.mjs --check   # exit 1 when the committed file drifted
 *
 * A userscript cannot import modules, so the build strips the `export` keywords
 * and wraps the source in an IIFE after the `==UserScript==` metadata block.
 * Pure helpers are unit-tested directly from `companion.mjs`; the generated
 * file is what the E2E suite and the browser actually run.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(HERE, "companion.mjs");
const TARGET = resolve(HERE, "../public/galleryvault-companion.user.js");

/** Keep in sync with META in companion.mjs (plain text: the header is not JS). */
export const HEADER_LINES = [
  "// ==UserScript==",
  "// @name         GalleryVault Companion",
  "// @version      0.1.0",
  "// @namespace    https://galleryvault.local/companion",
  "// @description  在 E-Hentai / ExHentai 画廊页显示 GalleryVault 库内状态，并一键下载 / 收藏 / 打开。阅读增强请搭配 Comic Looms。",
  "// @author       GalleryVault",
  "// @match        https://e-hentai.org/g/*",
  "// @match        https://exhentai.org/g/*",
  "// @grant        GM_xmlhttpRequest",
  "// @grant        GM_getValue",
  "// @grant        GM_setValue",
  "// @connect      *",
  "// @run-at       document-idle",
  "// @noframes",
  "// ==/UserScript==",
];

const BANNER = [
  "/*",
  " * GalleryVault Companion — generated file, do not edit.",
  " * Source: userscript/companion.mjs · rebuild with `node userscript/build.mjs`.",
  " */",
];

/** Strip ESM syntax so the source can run as a classic userscript. */
export function stripModuleSyntax(source) {
  return source
    .replace(/^export\s+(?=(?:async\s+)?function\b|const\b|let\b|class\b)/gm, "")
    .replace(/^export\s*\{[^}]*\};?\s*$/gm, "")
    .replace(/^import\s.+$/gm, "");
}

/** Render the complete userscript text from the module source. */
export function renderUserScript(source) {
  const body = stripModuleSyntax(source).trimEnd();
  return `${HEADER_LINES.join("\n")}\n${BANNER.join("\n")}\n(function () {\n  "use strict";\n\n${body}\n\n  init();\n})();\n`;
}

function main(argv) {
  const source = readFileSync(SOURCE, "utf8");
  const rendered = renderUserScript(source);
  const check = argv.includes("--check");
  if (check) {
    let current = "";
    try {
      current = readFileSync(TARGET, "utf8");
    } catch {
      console.error(`[userscript] missing ${TARGET}`);
      return 1;
    }
    if (current !== rendered) {
      console.error("[userscript] public/galleryvault-companion.user.js is stale — run `node userscript/build.mjs`");
      return 1;
    }
    console.log("[userscript] up to date");
    return 0;
  }
  writeFileSync(TARGET, rendered, "utf8");
  console.log(`[userscript] wrote ${TARGET} (${Buffer.byteLength(rendered)} bytes)`);
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main(process.argv.slice(2)));
}
