# AGENTS.md

Future agents must:

- Work only inside this project folder unless explicitly asked otherwise.
- Do not use paid APIs, API keys, secrets, Docker requirements or large real datasets for v0.1-style work.
- Do not overclaim exact fish locations, guaranteed fish schools, live fish GPS or certain catch prediction.
- Use language such as habitat suitability, hotspot score, bite probability, likely productive zone and fishing decision support.
- Keep legal and safety disclaimers visible in product and documentation.
- Keep mock data clearly labelled with `demo_only: true`.
- Add or update backend tests for scoring changes.
- Prefer small, reviewable changes.

Backend commands:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend commands:

```bash
cd frontend
npm install
npm run dev
npm run build
```
