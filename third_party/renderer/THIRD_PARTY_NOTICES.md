# Local diagram renderer notices

This directory accompanies the local diagram-rendering runtime distributed with
the application. It records the licenses and corresponding source for the
specific renderer build selected by `@viz-js/viz` 3.28.0.

These notices apply only to the third-party components named below. They do not
select, grant, or imply a license for the application or repository as a whole.

| Component | Exact identity | License | Distributed role |
| --- | --- | --- | --- |
| Viz.js | `@viz-js/viz` 3.28.0, source commit `b9f689720033ec89b678cf0b151817728b6be1de` | MIT | JavaScript API and WebAssembly bundle |
| Graphviz | 15.0.0 | Eclipse Public License 2.0 | Graph layout and rendering object code inside the Viz.js bundle |
| Expat | 2.8.1 | MIT | XML parsing object code inside the Viz.js bundle |
| Emscripten | 5.0.5 | MIT or University of Illinois/NCSA | Compiler/runtime used to produce the WebAssembly bundle |
| musl | Snapshot bundled by Emscripten 5.0.5 | MIT and the additional permissive notices in its `COPYRIGHT` file | C library code used by the Emscripten build |

Full upstream texts are included under `licenses/`. Exact source URLs, archive
checksums, and local license-file checksums are machine-readable in
`components.json`.

Graphviz is distributed under EPL-2.0. Its corresponding-source availability
and verification instructions are in [SOURCE_AVAILABILITY.md](SOURCE_AVAILABILITY.md).

The `@viz-js/viz` distribution also retains this notice in its generated
JavaScript banner:

> Viz.js 3.28.0 — Copyright (c) Michael Daines. This distribution contains
> other software in object code form: Graphviz and Expat.

Primary provenance:

- Viz.js release source and build recipe:
  <https://github.com/mdaines/viz-js/tree/b9f689720033ec89b678cf0b151817728b6be1de/packages/viz>
- Graphviz 15.0.0 release:
  <https://gitlab.com/graphviz/graphviz/-/releases/15.0.0>
- Expat 2.8.1 release:
  <https://github.com/libexpat/libexpat/releases/tag/R_2_8_1>
- Emscripten 5.0.5 source:
  <https://github.com/emscripten-core/emscripten/tree/5.0.5>
