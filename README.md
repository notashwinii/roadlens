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

The React dev server runs on `http://localhost:5173` and proxies `/api` to
`http://localhost:8000`.

## Current Direction

The Python backend remains the source of truth for video processing, OCR,
rules, evidence persistence, and migrations. The React frontend is the new
product surface for camera operations, processing jobs, violation review, and
configuration.
