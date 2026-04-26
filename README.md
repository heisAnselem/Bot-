# Bot- (Levanter-style FastAPI bot)

Deployable FastAPI bot backend with self-serve environment setup, Postgres storage, and WhatsApp-style session onboarding.

## What this supports
- Cloud deployment with environment variables (no hardcoded secrets)
- Free Postgres providers (Neon/Supabase)
- Session ID generation when a WhatsApp phone number is connected
- Bot webhook with command handling and message logging
- Optional Docker usage (for users who still want containers)

## API
- `GET /health` → health check
- `GET /setup/env-vars` → required/optional env vars for self-deploy
- `POST /whatsapp/connect` → connect phone number and generate/reuse `session_id`
- `POST /webhook` → send incoming messages (supports optional `session_id`)

### Connect phone and get session
Request:
```json
{
  "phone_number": "+2348012345678"
}
```

Response:
```json
{
  "phone_number": "+2348012345678",
  "session_id": "<generated_secure_token>",
  "status": "connected"
}
```

### Send message
Request:
```json
{
  "sender": "user-123",
  "message": "help",
  "session_id": "<generated_secure_token>"
}
```

## Supported built-in commands
`hello`, `ping`, `about`, `help`, `alive`, `owner`, `runtime`, `echo <text>`

## Environment variables
Required:
- `DATABASE_URL`

Common optional:
- `ENVIRONMENT`
- `BOT_NAME`
- `REQUIRE_SESSION_ID` (`true`/`false`)
- `DEFAULT_SESSION_ID`
- `ADMIN_PHONE_NUMBER`
- `WHATSAPP_API_URL`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

## Self-deploy (FastAPI cloud/ASGI platforms)
1. Fork/push this repository.
2. Create a free Postgres database on Neon or Supabase.
3. Add env vars in your deployment platform.
4. Deploy with startup command:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

## Local run
```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Docker (optional)
Docker is still included for users who prefer container deployment:
```bash
docker build -t bot-fastapi .
docker run -p 8000:8000 --env-file .env bot-fastapi
```
