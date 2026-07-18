# RoadLens

RoadLens is now organized as a two-part application:

```text
roadlens/
|-- backend/   # Python ALPR pipeline, Streamlit demo, DB models, migrations
`-- frontend/  # React operations dashboard
```

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --config configs/default.yaml
```

API server for the React app:

```bash
cd backend
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

Processing worker:

```bash
cd backend
python -m jobs.worker
```

Streamlit demo:

```bash
cd backend
streamlit run app.py
```

Docker demo:

```bash
cd backend
docker compose -f docker/docker-compose.yml up --build web
```

## Frontend

```bash
cd frontend
bun install
bun run dev
```

The React dev server runs on `http://localhost:5173` and proxies `/api` to the
backend API on `http://localhost:8000`.

## Current Direction

The Python backend remains the source of truth for video processing, OCR,
rules, evidence persistence, API contracts, and migrations. The React frontend is
the product surface for authentication, workspaces, team roles, camera operations,
camera-frame zone drawing, queued processing, rules, violation review, and
configuration. The API and `python -m jobs.worker` share persisted processing
jobs so long-running detection does not block web requests. Persisted camera
configurations can also be processed directly with
`python main.py --camera-id <database-id>`. YAML remains supported for portable
CLI and local demo runs.
