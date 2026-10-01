import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.dirname(frontendRoot);
const distRoot = path.join(frontendRoot, "dist");
const sourceHtmlPath = path.join(appRoot, "static", "index.html");
const entryPoint = path.join(frontendRoot, "src", "app.ts");

const sourceStylesheetPattern = /<link rel="stylesheet" href="\/static\/css\/main\.css(?:\?[^"\s]*)?" \/>/g;
const sourceModulePattern = /<script type="module" src="\/static\/js\/main\.js(?:\?[^"\s]*)?"><\/script>/g;
const sourceImportMapPattern = /    <!-- source-import-map:start -->\r?\n[\s\S]*?    <!-- source-import-map:end -->\r?\n/g;

function requireSingleMatch(text, pattern, description) {
  const matches = [...text.matchAll(pattern)];
  if (matches.length !== 1) {
    throw new Error(`Expected exactly one ${description}; found ${matches.length}.`);
  }
  return matches[0][0];
}

function relativeOutputPath(outputPath) {
  const absoluteOutputPath = path.resolve(appRoot, outputPath);
  const relative = path.relative(distRoot, absoluteOutputPath);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Build output escaped the frontend distribution directory: ${outputPath}`);
  }
  return relative.split(path.sep).join("/");
}

await rm(distRoot, { recursive: true, force: true });
await mkdir(distRoot, { recursive: true });

const result = await build({
  absWorkingDir: appRoot,
  assetNames: "assets/[name]-[hash]",
  bundle: true,
  charset: "utf8",
  chunkNames: "assets/[name]-[hash]",
  entryNames: "assets/[name]-[hash]",
  entryPoints: [path.relative(appRoot, entryPoint)],
  format: "esm",
  legalComments: "eof",
  logLevel: "info",
  metafile: true,
  minify: true,
  outdir: distRoot,
  platform: "browser",
  sourcemap: false,
  splitting: true,
  target: ["es2022"],
  write: true,
});

const normalizedEntryPoint = path.relative(appRoot, entryPoint).split(path.sep).join("/");
const outputEntries = Object.entries(result.metafile.outputs).map(([outputPath, metadata]) => ({
  metadata,
  outputPath: relativeOutputPath(outputPath),
}));
const javascriptOutputs = outputEntries
  .filter(
    ({ metadata, outputPath }) =>
      metadata.entryPoint?.replaceAll("\\", "/") === normalizedEntryPoint && outputPath.endsWith(".js"),
  )
  .map(({ outputPath }) => outputPath);
const stylesheetOutputs = outputEntries
  .filter(({ outputPath }) => outputPath.endsWith(".css"))
  .map(({ outputPath }) => outputPath);

if (javascriptOutputs.length !== 1 || stylesheetOutputs.length !== 1) {
  throw new Error(
    `Expected one JavaScript and one CSS output; found ${javascriptOutputs.length} JavaScript and ${stylesheetOutputs.length} CSS outputs.`,
  );
}

const vizOutputs = outputEntries.filter(({ metadata, outputPath }) => {
  if (!outputPath.endsWith(".js")) {
    return false;
  }
  return Object.keys(metadata.inputs).some((inputPath) =>
    inputPath.replaceAll("\\", "/").endsWith("node_modules/@viz-js/viz/dist/viz.js"),
  );
});
if (vizOutputs.length !== 1 || vizOutputs[0].outputPath === javascriptOutputs[0]) {
  throw new Error(`Expected one lazy Viz.js chunk distinct from the application entry; found ${vizOutputs.length}.`);
}

const assetPaths = outputEntries.map(({ outputPath }) => outputPath).sort();
for (const outputPath of assetPaths) {
  if (!/^assets\/[^/]+-[A-Z0-9]{8}\.[A-Za-z0-9.]+$/.test(outputPath)) {
    throw new Error(`Expected a content-hashed frontend asset; received ${outputPath}.`);
  }
  if (outputPath.endsWith(".wasm")) {
    throw new Error("@viz-js/viz must remain a self-contained JavaScript chunk; an unexpected WASM file was emitted.");
  }
}

const javascriptUrl = `/static/${javascriptOutputs[0]}`;
const stylesheetUrl = `/static/${stylesheetOutputs[0]}`;
const vizUrl = `/static/${vizOutputs[0].outputPath}`;
const manifest = {
  schema_version: 2,
  assets: assetPaths.map((outputPath) => `/static/${outputPath}`),
  chunks: {
    viz: vizUrl,
  },
  entrypoints: {
    app: {
      javascript: javascriptUrl,
      stylesheet: stylesheetUrl,
    },
  },
};

const sourceHtml = await readFile(sourceHtmlPath, "utf8");
requireSingleMatch(sourceHtml, sourceStylesheetPattern, "development stylesheet reference");
requireSingleMatch(sourceHtml, sourceModulePattern, "development module reference");
requireSingleMatch(sourceHtml, sourceImportMapPattern, "development import map");

const productionHtml = sourceHtml
  .replace(sourceImportMapPattern, "")
  .replace(sourceStylesheetPattern, `<link rel="stylesheet" href="${stylesheetUrl}" />`)
  .replace(sourceModulePattern, `<script type="module" src="${javascriptUrl}"></script>`);

await writeFile(path.join(distRoot, "asset-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
await writeFile(path.join(distRoot, "index.html"), productionHtml, "utf8");
