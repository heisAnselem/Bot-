# Bot- (A-bot WhatsApp backend)

Deployable FastAPI backend for **A-bot** with WhatsApp-only access, session onboarding, and a built-in web control interface.

## What this supports
- Cloud deployment with environment variables (no hardcoded secrets)
- Free Postgres providers (Neon/Supabase)
- User login/register and personal workspace management
- Session ID generation when each user connects a WhatsApp phone number
- Web interface at `GET /` for login, runtime view, database profile setup, and session generation
- Bot webhook with command handling and message logging
- Prefix-based WhatsApp commands (default prefix `.`)
- Optional Docker usage (for users who still want containers)

## API
- `GET /health` → health check
- `GET /` → A-bot control interface (register/login + workspace manager)
- `GET /setup/env-vars` → required/optional env vars for self-deploy
- `POST /auth/register` → create user and return access token
- `POST /auth/login` → login and return access token
- `GET /me/overview` → authenticated workspace stats/sessions/database profile
- `POST /me/database/connect` → verify and save Neon/Supabase DB profile (masked URL)
- `POST /whatsapp/connect` → authenticated connect phone number and generate/reuse `session_id`
- `POST /webhook` → WhatsApp-only message webhook (`sender` must be phone/JID and `session_id` is required by default)

### Register/login response
```json
{
  "token": "<bearer_token>",
  "email": "user@example.com"
}
```

### Connect phone and get session (authenticated)
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

### Send WhatsApp message
Request:
```json
{
  "sender": "2348012345678@s.whatsapp.net",
  "message": ".menu",
  "session_id": "<generated_secure_token>"
}
```

## Supported built-in commands
Use configured prefix (default `.`), for example:
- `.menu` (full Levanter-style menu layout)
- `.ping`
- `.alive`
- `.about`
- `.owner`
- `.runtime`
- `.echo hello`

## Normal WhatsApp usage
- Open `GET /` and create account/login.
- Connect your free DB profile (Neon/Supabase) in the dashboard.
- Generate/reuse a session ID with your WhatsApp phone number.
- Connect your WhatsApp bridge/client and forward incoming messages to `POST /webhook`.
- If you use **Baileys**, keep it as the WhatsApp transport layer and post received messages to this API.

## Environment variables
Required:
- `DATABASE_URL`

Common optional:
- `ENVIRONMENT`
- `BOT_NAME`
- `COMMAND_PREFIX` (default `.`)
- `WHATSAPP_ONLY` (`true`/`false`, default `true`)
- `REQUIRE_SESSION_ID` (`true`/`false`)
- `MAX_SESSION_ID_GENERATION_ATTEMPTS` (default `5`)
- `DEFAULT_SESSION_ID`
- `ADMIN_PHONE_NUMBER`
- `LEVANTER_VERSION` (display-only text in menu header)
- `LEVANTER_PLUGINS` (display-only text in menu header)
- `WHATSAPP_API_URL`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

## Self-deploy (FastAPI cloud/ASGI platforms)
1. Fork/push this repository.
2. Create a free Postgres database on Neon or Supabase.
3. Set that database URL as `DATABASE_URL` in your FastAPI cloud deployment.
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
