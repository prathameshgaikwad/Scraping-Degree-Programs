# ProgramMatch frontend

React (Vite) UI for the Master's Program Intelligence engine. **Live backend
only** — every program, requirement and eligibility figure comes from the API at
request time; there is no bundled snapshot.

## Run

Everything is served by the Python backend on **one port**. From the repo root:

```bash
npm start                 # builds the UI, then serves API + UI at :8000
```

Then open http://127.0.0.1:8000/.

Or run the steps separately:

```bash
npm run build:ui          # compile this frontend into the backend's static dir
npm run serve             # python -m degreeprograms.cli serve  -> :8000
```

## Scripts

- `npm run build` / `npm run build:serve` — production build into
  `../degreeprograms/webapp/static/app` (the directory the backend serves at `/`).

## Notes

- There is no separate Vite dev server: the backend serves the built bundle and
  the API on the same origin, so no proxy or CORS is needed.
- `src/lib/backend.js` is the single API adapter (field/enum mapping, model
  shaping). `VITE_API_BASE` is an optional override for unusual deployments.
