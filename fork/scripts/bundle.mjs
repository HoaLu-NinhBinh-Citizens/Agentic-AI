#!/usr/bin/env node
// Bundle aircode into the cloned VS Code as a built-in extension, and place the
// aircore daemon binary alongside it so the packaged app is self-contained.
//
// Assumes: clone.mjs + rebrand.mjs have run, the extension is compiled
// (editor-extension/out exists), and the daemon is built (release binary).

import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(readFileSync(resolve(here, "../config/fork.config.json"), "utf8"));

const cloneDir = resolve(here, "..", cfg.cloneDir);
const extSrc = resolve(here, "..", cfg.extensionDir);
const daemonDir = resolve(here, "..", cfg.daemonCrateDir);
const exe = process.platform === "win32" ? `${cfg.daemonBinary}.exe` : cfg.daemonBinary;

function die(msg) {
  console.error(`bundle: ${msg}`);
  process.exit(1);
}

if (!existsSync(cloneDir)) die(`clone missing — run clone.mjs first (${cloneDir})`);
if (!existsSync(resolve(extSrc, "out"))) die("extension not compiled — run `npm run compile` in editor-extension");

// 1) Copy the compiled extension into the clone as a built-in extension.
const dest = resolve(cloneDir, "extensions", cfg.builtinExtensionFolder);
rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
for (const item of ["package.json", "out", "README.md"]) {
  const from = resolve(extSrc, item);
  if (existsSync(from)) cpSync(from, resolve(dest, item), { recursive: true });
}

// 2) Bundle the daemon binary inside the extension so resolveDaemonPath finds
//    it next to the extension in the packaged app (./bin/<exe>).
const builtBinary = resolve(daemonDir, "target", "release", exe);
if (!existsSync(builtBinary)) {
  die(`daemon binary missing: ${builtBinary} — run \`cargo build --release\` (PROTOC set) in editor-core`);
}
const binDir = resolve(dest, "bin");
mkdirSync(binDir, { recursive: true });
cpSync(builtBinary, resolve(binDir, exe));

console.log(`bundled aircode -> ${dest}`);
console.log(`bundled daemon  -> ${resolve(binDir, exe)}`);
console.log("NOTE: ensure the extension's resolveDaemonPath also checks ./bin (see fork/README.md).");
