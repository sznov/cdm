import assert from "node:assert/strict";
import { copyFile, mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.dirname(frontendRoot);
const packageAsset = fileURLToPath(import.meta.resolve("@viz-js/viz"));
const expectedPackageSuffix = path.join("@viz-js", "viz", "dist", "viz.js");
const sourceAsset = path.join(appRoot, "static", "vendor", "viz.js");
const sourceHtml = path.join(appRoot, "static", "index.html");
const checkOnly = process.argv.slice(2).includes("--check");

assert.ok(
  packageAsset.endsWith(expectedPackageSuffix),
  `@viz-js/viz must resolve to its self-contained dist/viz.js; received ${packageAsset}`,
);

if (!checkOnly) {
  await mkdir(path.dirname(sourceAsset), { recursive: true });
  await copyFile(packageAsset, sourceAsset);
}

const [packageBytes, sourceBytes, html] = await Promise.all([
  readFile(packageAsset),
  readFile(sourceAsset),
  readFile(sourceHtml, "utf8"),
]);
assert.deepEqual(sourceBytes, packageBytes, "static/vendor/viz.js must exactly match @viz-js/viz dist/viz.js");
assert.match(
  html,
  /"@viz-js\/viz"\s*:\s*"\/static\/vendor\/viz\.js"/,
  "source HTML must map the bare @viz-js/viz specifier to the prepared local asset",
);

console.log(`${checkOnly ? "Verified" : "Prepared"} source Viz.js asset: ${sourceAsset}`);
