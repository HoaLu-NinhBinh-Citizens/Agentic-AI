#!/usr/bin/env node
// Rebrand a cloned VS Code by deep-merging product.overrides.json into the
// clone's product.json. Keys beginning with "_comment" are documentation only
// and are stripped. Exported `applyOverrides` is unit-testable offline.

import { readFileSync, realpathSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Deep-merge `over` into `base` (over wins); arrays replace; _comment* dropped. */
export function applyOverrides(base, over) {
  const out = Array.isArray(base) ? [...base] : { ...base };
  for (const [key, value] of Object.entries(over)) {
    if (key.startsWith("_comment")) continue;
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      out[key] &&
      typeof out[key] === "object" &&
      !Array.isArray(out[key])
    ) {
      out[key] = applyOverrides(out[key], value);
    } else {
      out[key] = value;
    }
  }
  return out;
}

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

// True when this file is the entry point (cross-platform; the naive
// `file://${argv[1]}` check fails on Windows path separators).
function isMain() {
  try {
    return process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

// CLI entry (skipped when imported by tests).
if (isMain()) {
  const productPath = arg("product");
  const overridesPath = arg("overrides", fileURLToPath(new URL("../config/product.overrides.json", import.meta.url)));
  if (!productPath) {
    console.error("usage: rebrand.mjs --product <clone>/product.json [--overrides <file>]");
    process.exit(2);
  }
  const product = JSON.parse(readFileSync(productPath, "utf8"));
  const overrides = JSON.parse(readFileSync(overridesPath, "utf8"));
  const merged = applyOverrides(product, overrides);
  writeFileSync(productPath, JSON.stringify(merged, null, "\t") + "\n");
  console.log(`rebranded ${productPath}: nameLong=${merged.nameLong}, appName=${merged.applicationName}`);
}
