# Bot- (Levanter-style FastAPI bot)

This repository now contains a lightweight Levanter-inspired bot backend built with **FastAPI**, ready for cloud deployment and configured to use a **free Postgres database provider**.

## Features
- FastAPI webhook endpoint for bot messages
- Built-in command handling (`hello`, `help`, `ping`, `about`)
- Message/reply logging to Postgres
- Dockerized for simple cloud deployment

## API
- `GET /health` → service health
- `POST /webhook` → send message payload

Example request:
```json
{
  "sender": "user-123",
  "message": "ping"
}
```

## Local run
1. Copy env file:
   ```bash
   cp .env.example .env
   ```
2. Set your database URL in `.env`.
3. Install and run:
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

## Free database provider
Use a free Postgres provider like:
- **Neon** (recommended)
- **Supabase**

Set:
- `DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require`

## Deploy on FastAPI Cloud
1. Push this repository to GitHub.
2. Create your database on Neon/Supabase and copy the connection URL.
3. Create a FastAPI Cloud project from this repo.
4. Add environment variables:
   - `ENVIRONMENT=production`
   - `DATABASE_URL=<your_postgres_url>`
5. Deploy.

The app starts with:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
