import assert from "node:assert";
import { test } from "node:test";

import { applyOverrides } from "./rebrand.mjs";

test("overrides replace scalar product fields", () => {
  const base = { nameShort: "Code - OSS", nameLong: "Code - OSS", applicationName: "code-oss" };
  const over = { nameShort: "aircode", nameLong: "aircode", applicationName: "aircode" };
  const out = applyOverrides(base, over);
  assert.equal(out.nameLong, "aircode");
  assert.equal(out.applicationName, "aircode");
});

test("nested objects deep-merge (gallery url swapped, other keys kept)", () => {
  const base = { extensionsGallery: { serviceUrl: "https://marketplace...", controlUrl: "keep-me" } };
  const over = { extensionsGallery: { serviceUrl: "https://open-vsx.org/vscode/gallery" } };
  const out = applyOverrides(base, over);
  assert.equal(out.extensionsGallery.serviceUrl, "https://open-vsx.org/vscode/gallery");
  assert.equal(out.extensionsGallery.controlUrl, "keep-me");
});

test("_comment keys are stripped, real keys survive", () => {
  const base = { updateUrl: "https://update.code..." };
  const over = { _comment_updateUrl: "docs", updateUrl: "" };
  const out = applyOverrides(base, over);
  assert.equal(out.updateUrl, "");
  assert.ok(!("_comment_updateUrl" in out));
});

test("base-only keys are preserved", () => {
  const base = { commit: "abc", date: "2026", nameLong: "Code - OSS" };
  const out = applyOverrides(base, { nameLong: "aircode" });
  assert.equal(out.commit, "abc");
  assert.equal(out.date, "2026");
  assert.equal(out.nameLong, "aircode");
});
