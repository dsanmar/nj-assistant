# NJDOT Assistant

Monorepo scaffold with a Next.js frontend and FastAPI backend for the NJDOT Assistant.

## Structure
- `frontend`: Next.js App Router + Tailwind + shadcn/ui-style components
- `backend`: FastAPI service with Supabase JWT verification
- `db`: placeholder schema

## Local setup

### Frontend
1. `cd frontend`
2. `cp .env.example .env.local` and fill in Supabase values
3. `npm install`
4. `npm run dev`

### Backend
1. `cd backend`
2. `cp .env.example .env`
3. `python -m venv .venv`
4. `source .venv/bin/activate`
5. `pip install -r requirements.txt`
6. `uvicorn app.main:app --reload --port 8000`

## Notes
- `/chat`, `/documents` are protected by Supabase auth.
- `/chat` returns a mocked response that matches the schema.
