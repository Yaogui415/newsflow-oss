# Self-Hosting NewsFlow

This document explains the simplest way to run NewsFlow on your own machine or in a small self-hosted environment.

## What to expect

NewsFlow currently works best as a self-hosted prototype for:

- product exploration
- workflow demos
- teaching and discussion
- internal tooling experiments

It is not yet presented as a production-ready newsroom platform.

## Architecture overview

A local setup usually includes:

- frontend (`frontend/`) — React + Vite
- backend (`backend/`) — FastAPI
- database — SQLite for the easiest local start, PostgreSQL for a more realistic setup
- optional services — Redis, MinIO, Elasticsearch

For the fastest start, you can run the backend with SQLite and the frontend with Vite.

## Recommended local versions

- Python `3.12` or `3.13`
- Node.js `20.19+`
- Docker Desktop or another local Docker runtime

Python `3.14` is not currently recommended for this repository because some native dependencies, especially `orjson`, may fail to build in certain environments.

## Option A: fastest local setup

### 1. Start infrastructure

From the project root:

```bash
docker compose up -d
```

### 2. Configure the backend

```bash
cp backend/.env.example backend/.env
```

Recommended local values:

- keep `DATABASE_URL=sqlite+aiosqlite:///./newsflow.db` for the simplest setup
- leave `OPENAI_API_KEY=` empty if you only want to explore non-LLM paths
- set `SECRET_KEY` to your own local random string
- set `SOURCE_VAULT_ENCRYPTION_KEY` to your own local random string

### 3. Configure the frontend

```bash
cp frontend/.env.example frontend/.env.local
```

Default local API target:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 4. Start the backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 6. Open the app

- frontend: `http://localhost:5173`
- health: `http://localhost:8000/health`
- docs: `http://localhost:8000/docs`

## Option B: use PostgreSQL instead of SQLite

If you want a setup closer to real multi-user usage, switch the backend to PostgreSQL.

Example:

```env
DATABASE_URL=postgresql+asyncpg://newsflow:newsflow@localhost:5432/newsflow
```

Then run:

```bash
cd backend
alembic upgrade head
```

## Optional integrations

### OpenAI / LLM support

Set the following in `backend/.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=
LLM_MODEL=gpt-4o-mini
```

If `OPENAI_API_KEY` is empty, parts of the system may still run, but LLM-backed behavior will be limited.

### Redis

Redis is useful for caching and future async work patterns.

```env
REDIS_URL=redis://localhost:6379/0
```

### MinIO

If you want object storage support:

```env
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

### Elasticsearch

If you want to extend search or audit indexing:

```env
ELASTICSEARCH_URL=http://localhost:9200
```

## Deployment notes

### Frontend

The frontend is easiest to deploy on:

- Vercel
- Netlify
- any static hosting service that supports SPA routing

Make sure `VITE_API_BASE_URL` points to your backend.

### Backend

The backend can be deployed on:

- Render
- Railway
- Fly.io
- your own VM or container host

Do not commit real credentials into `render.yaml`, `.env`, or any deployment manifest.

## Sensitive data rules

If you self-host NewsFlow, do not use public or demo environments for:

- real source-protection data
- unpublished reporting notes
- real personal contact information
- real internal approval history from a newsroom

## Common issues

### Frontend cannot reach backend

Check:

- backend is running on port `8000`
- `frontend/.env.local` has the correct `VITE_API_BASE_URL`
- backend CORS settings allow your local frontend origin

### Backend starts but some features fail

Check:

- whether `OPENAI_API_KEY` is configured
- whether your database migrations have run
- whether optional services like Redis or MinIO are expected by the path you are testing

### GitHub Actions or CI does not match local behavior

This repository currently uses a lightweight CI path. Some advanced agent or integration behaviors may require local services or API keys that CI does not provide by default.
