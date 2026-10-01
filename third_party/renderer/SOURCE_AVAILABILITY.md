# Graphviz corresponding source

The local renderer includes Graphviz 15.0.0 object code inside the
`@viz-js/viz` 3.28.0 JavaScript/WebAssembly bundle. Graphviz is made available
under the Eclipse Public License 2.0; the complete license is included at
`licenses/graphviz-EPL-2.0.txt`.

The exact corresponding source archive used by the upstream Viz.js build recipe
is available through Graphviz's official GitLab package registry:

- URL:
  <https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/15.0.0/graphviz-15.0.0.tar.gz>
- SHA-256:
  `06193df2f54cf0a505e6a2d154ed5df64d2e9ced50f8bf6e454049c1a59c8fd6`

Download that archive and verify it before use:

```text
sha256sum graphviz-15.0.0.tar.gz
```

The expected digest is the value above. The source archive is the preferred
form for modifying Graphviz. The Viz.js 3.28.0 build recipe downloads that
archive and compiles it with Emscripten 5.0.5; the recipe is available at:

<https://github.com/mdaines/viz-js/blob/b9f689720033ec89b678cf0b151817728b6be1de/packages/viz/backend/Dockerfile>

The application repository does not carry a modified Graphviz source tree and
does not apply application-specific Graphviz patches. This statement concerns
Graphviz only and does not select a license for the application as a whole.
