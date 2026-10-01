FROM python:3.14.6-alpine3.24@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92 AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY requirements-linux.lock ./
RUN python -m pip install --require-hashes -r requirements-linux.lock \
    && python -m pip check

FROM node:24.18.0-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS node-toolchain

FROM node-toolchain AS frontend-builder

ENV CI=1

WORKDIR /workspace

COPY package.json package-lock.json ./
RUN expected_node="$(node -p 'require("./package.json").engines.node')" \
    && expected_npm="$(node -p 'require("./package.json").engines.npm')" \
    && test "$(node --version)" = "v${expected_node}" \
    && test "$(npm --version)" = "${expected_npm}" \
    && npm ci

COPY . .
RUN npm run build:frontend

FROM python-base AS runtime-source

ARG CDMAPP_GIT_COMMIT=""

COPY . .
COPY --from=frontend-builder /workspace/frontend/dist ./frontend/dist

RUN python -m core.build_provenance \
        --mode docker \
        --output build/build-identity.json \
        --git-state unavailable \
        --git-commit "$CDMAPP_GIT_COMMIT"

FROM python-base AS runtime

COPY --from=runtime-source /workspace/main.py ./main.py
COPY --from=runtime-source /workspace/LICENSE ./LICENSE
COPY --from=runtime-source /workspace/backend ./backend
COPY --from=runtime-source /workspace/core ./core
COPY --from=runtime-source /workspace/harnesses ./harnesses
COPY --from=runtime-source /workspace/judge ./judge
COPY --from=runtime-source /workspace/frontend/dist ./frontend/dist
COPY --from=runtime-source /workspace/build/build-identity.json ./build/build-identity.json
COPY --from=runtime-source /workspace/third_party/renderer ./third_party/renderer

ENV CONCEPTUAL_MODEL_GENERATOR_STATIC_DIR=/workspace/frontend/dist \
    CDMAPP_BUILD_IDENTITY_PATH=/workspace/build/build-identity.json

RUN test -f frontend/dist/index.html \
    && test -f LICENSE \
    && test -f frontend/dist/asset-manifest.json \
    && test -f build/build-identity.json \
    && test -f third_party/renderer/THIRD_PARTY_NOTICES.md \
    && test -f third_party/renderer/SOURCE_AVAILABILITY.md \
    && test -f third_party/renderer/components.json \
    && test -f third_party/renderer/licenses/viz-js-MIT.txt \
    && test -f third_party/renderer/licenses/graphviz-EPL-2.0.txt \
    && test -f third_party/renderer/licenses/expat-MIT.txt \
    && test -f third_party/renderer/licenses/emscripten-MIT-NCSA.txt \
    && test -f third_party/renderer/licenses/musl-COPYRIGHT.txt \
    && test ! -d tests \
    && test ! -d scripts \
    && test ! -d node_modules \
    && test ! -f package.json \
    && test ! -f package-lock.json \
    && ! command -v node \
    && ! command -v npm

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
