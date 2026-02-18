# NJDOT Assistant

Monorepo scaffold with a Next.js frontend and FastAPI backend for the NJDOT Assistant.

## Structure
- `frontend`: Next.js App Router + Tailwind + shadcn/ui-style components
- `backend`: FastAPI service with Supabase JWT verification
- `db`: placeholder schema

## Local setup

### Frontend
1. `cd frontend`
2. `cp .env.local.example .env.local` and fill in Supabase values
3. `npm install`
4. `npm run dev`

### Backend
1. `cd backend`
2. `cp .env.example .env`
   - Set `LLM_PROVIDER` to `openai`, `groq`, `ollama`, or `mock`
3. `python -m venv .venv`
4. `source .venv/bin/activate`
5. `pip install -r requirements.txt`
6. `uvicorn app.main:app --reload --port 8000`

### Ollama (optional, for local LLM)
If you want to use `LLM_PROVIDER=ollama`, install Ollama and pull a model.

**macOS**
1. Install the Ollama desktop app from the official macOS installer
2. Confirm the CLI is available: `ollama --version`
3. Pull a model: `ollama pull llama3.1`

**Windows**
1. Install Ollama using the official Windows installer.
2. Confirm the CLI is available: `ollama --version`
3. Pull a model: `ollama pull llama3.1`
