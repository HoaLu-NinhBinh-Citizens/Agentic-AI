#!/usr/bin/env node
// Shallow-clone upstream VS Code at the pinned tag (idempotent). Reads
// fork/config/fork.config.json. The clone is large (~hundreds of MB) and is
// git-ignored — it is a build input, never committed.

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(readFileSync(resolve(here, "../config/fork.config.json"), "utf8"));
const cloneDir = resolve(here, "..", cfg.cloneDir);

function run(cmd, args, opts = {}) {
  console.log(`$ ${cmd} ${args.join(" ")}`);
  execFileSync(cmd, args, { stdio: "inherit", ...opts });
}

if (existsSync(cloneDir)) {
  console.log(`clone exists at ${cloneDir}; fetching tag ${cfg.pinnedTag}`);
  run("git", ["-C", cloneDir, "fetch", "--depth", "1", "origin", "tag", cfg.pinnedTag]);
  run("git", ["-C", cloneDir, "checkout", "-f", `tags/${cfg.pinnedTag}`]);
} else {
  console.log(`cloning ${cfg.upstream} @ ${cfg.pinnedTag} -> ${cloneDir}`);
  run("git", [
    "clone",
    "--depth", "1",
    "--branch", cfg.pinnedTag,
    cfg.upstream,
    cloneDir,
  ]);
}
console.log("clone ready.");
