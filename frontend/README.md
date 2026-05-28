# Frontend

Next.js TypeScript dashboard for the Sydney Offshore Pelagic AI Map v0.1 demo.

## Run

```bash
cd sydney-offshore-pelagic-ai/frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

For the most stable local demo, build and serve the static export:

```bash
cd sydney-offshore-pelagic-ai/frontend
npm run build
npm run serve:static
```

Open `http://127.0.0.1:3000`.

Set `NEXT_PUBLIC_API_BASE_URL` only if the backend is not at `http://localhost:8000/api`.
The UI includes fallback mock data so it can render when the backend is offline.
