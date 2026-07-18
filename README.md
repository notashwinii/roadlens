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

## Staging and production

The production Compose stack exposes only the nginx frontend. nginx serves the
React application and proxies `/api` to FastAPI over the private Compose
network. MariaDB, uploaded camera files, and evidence outputs use persistent
named volumes.

Create the deployment environment:

```bash
cp .env.example .env.production
```

Replace every `change-me` value. In particular, generate a stable encryption
key for camera credentials:

```bash
openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
```

Start the database, migration gate, API, processing worker, and frontend:

```bash
docker compose \
  --env-file .env.production \
  -f compose.production.yml \
  up -d --build
```

Check the deployment:

```bash
docker compose --env-file .env.production -f compose.production.yml ps
curl http://localhost:8080/api/ready
```

Terminate TLS at the host load balancer or reverse proxy and forward traffic to
`ROADLENS_HTTP_PORT`. Keep `ROADLENS_COOKIE_SECURE=true` behind HTTPS. For a
local HTTP-only Compose test, set it to `false`.

The `ROADLENS_MASTER_KEY` must remain stable across API and worker restarts.
Changing it makes existing encrypted camera credentials unreadable. Back up the
`database_data`, `camera_uploads`, and `evidence_outputs` volumes together.

CI in `.github/workflows/ci.yml` runs backend lint/tests, a clean migration,
frontend lint/build, and Compose validation for every pull request.

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
