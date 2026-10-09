// Run with: npm test   (Node's built-in runner; compiles the two small source files with the installed TypeScript)
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, ".test-build");
const require = createRequire(import.meta.url);

let React, renderToStaticMarkup, DecisionLinks, links;

function compile(srcRelative, outRelative) {
  const source = fs.readFileSync(path.join(root, srcRelative), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  });
  const outPath = path.join(outDir, outRelative);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, outputText);
  return outPath;
}

before(() => {
  compile("src/lib/decisionLinks.ts", "lib/decisionLinks.js");
  const componentPath = compile("src/components/DecisionLinks.tsx", "components/DecisionLinks.js");
  // CommonJS output must be loaded from a directory that is not treated as ESM
  fs.writeFileSync(path.join(outDir, "package.json"), JSON.stringify({ type: "commonjs" }));
  React = require("react");
  ({ renderToStaticMarkup } = require("react-dom/server"));
  DecisionLinks = require(componentPath).default;
  links = require(path.join(outDir, "lib/decisionLinks.js"));
});

after(() => {
  fs.rmSync(outDir, { recursive: true, force: true });
});

const render = (props) => renderToStaticMarkup(React.createElement(DecisionLinks, props));

// ---------------------------------------------------------------- navigation target
test("Explore Decision links to the Decision Explorer with the real decision id", () => {
  assert.equal(links.decisionExplorerHref("dec_b3d629c9047c"), "/decisions?id=dec_b3d629c9047c");
});

test("the id survives a round trip through the URL, including unusual characters", () => {
  for (const id of ["dec_abc123", "dec with space", "dec&id=other", "dec/ä?"]) {
    const search = new URL(links.decisionExplorerHref(id), "http://localhost").search;
    assert.equal(links.decisionIdFromSearch(search), id);
  }
});

test("the explorer ignores a missing or blank id", () => {
  assert.equal(links.decisionIdFromSearch(""), null);
  assert.equal(links.decisionIdFromSearch("?other=1"), null);
  assert.equal(links.decisionIdFromSearch("?id="), null);
  assert.equal(links.decisionIdFromSearch("?id=%20%20"), null);
});

// ---------------------------------------------------------------- rendering
test("renders a decision id with an Explore Decision link to that exact id", () => {
  const html = render({ decisionIds: ["dec_b3d629c9047c"] });
  assert.match(html, /<code>dec_b3d629c9047c<\/code>/);
  assert.match(html, /href="\/decisions\?id=dec_b3d629c9047c"/);
  assert.match(html, /Explore Decision/);
  assert.match(html, /<strong>Decision<\/strong>/);
});

test("renders every decision when a document has several, each linking to its own id", () => {
  const html = render({ decisionIds: ["dec_abc123", "dec_def456"] });
  for (const id of ["dec_abc123", "dec_def456"]) {
    assert.match(html, new RegExp(`<code>${id}</code>`));
    assert.match(html, new RegExp(`href="/decisions\\?id=${id}"`));
  }
  assert.equal((html.match(/Explore Decision/g) ?? []).length, 2);
  assert.ok(html.indexOf("dec_abc123") < html.indexOf("dec_def456"), "order is preserved");
});

test("a document with no decisions shows 'None extracted' and no link or fake id", () => {
  const html = render({ decisionIds: [] });
  assert.match(html, /None extracted/);
  assert.doesNotMatch(html, /<a /);
  assert.doesNotMatch(html, /dec_/);
  assert.doesNotMatch(html, /Explore Decision/);
});

test("the inline label can be hidden (success card supplies its own heading)", () => {
  const html = render({ decisionIds: ["dec_abc123"], showLabel: false });
  assert.match(html, /<code>dec_abc123<\/code>/);
  assert.doesNotMatch(html, /<strong>Decision<\/strong>/);
});

test("each link is labelled for screen readers with its id", () => {
  const html = render({ decisionIds: ["dec_abc123"] });
  assert.match(html, /aria-label="Explore decision dec_abc123"/);
});
