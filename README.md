# Conceptual Model Generator

An LLM-based, single-user application for drafting and refining conceptual
database models from textual requirements, with a local browser interface.

## Docker

Copy `.env.example` to `.env`:

```sh
cp .env.example .env
```

On Windows, use `Copy-Item .env.example .env`. Add your own provider API keys
to `.env`, then run:

```sh
docker compose up --build
```

Open <http://127.0.0.1:8010>. The service binds only to localhost and stores runs
under `__db__/`. Keep that directory and `.env` private. Provider calls may cost
money.

## Run from source

Use Python 3.14.6 and Node.js 24.18.0 with npm 11.16.0. Create and activate a
Python virtual environment, then run:

```sh
python -m pip install -r requirements.txt
npm ci
npm run prepare:source-assets
python -m uvicorn main:app --host 127.0.0.1 --port 8010
```

For bundled frontend assets, use `npm run build:frontend` and set
`CONCEPTUAL_MODEL_GENERATOR_STATIC_DIR` to the absolute `frontend/dist` path.

## Workflows and evaluation

The default workflow is `structured-patch-refined-v2`. A legacy workflow,
`gemma4-tuned-final-20260524`, is also selectable and includes a language-repair
pass. The two workflows can produce different results.

Generation and evaluation entry points live in `scripts/`. See
[EVALUATION.md](EVALUATION.md) to use your own dataset. Datasets and evaluation
outputs are not included.

## License

[MIT](LICENSE). You may use, modify, and redistribute the code, including
commercially, while retaining the license notice. Third-party components retain
their [own licenses](third_party/renderer/THIRD_PARTY_NOTICES.md).
