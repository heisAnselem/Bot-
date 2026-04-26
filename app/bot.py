def generate_reply(message: str) -> str:
    text = (message or "").strip()
    normalized = text.lower()

    if not text:
        return "Send a message and I’ll respond."
    if normalized in {"hi", "hello", "hey"}:
        return "Hello 👋 I am your Levanter-style FastAPI bot."
    if normalized in {"help", "menu", "commands"}:
        return "Commands: hi/hello/hey, ping, about, help, alive, owner, runtime, echo <text>"
    if normalized == "ping":
        return "pong"
    if normalized in {"alive", "status"}:
        return "I am alive and running ✅"
    if normalized == "owner":
        return "Owner can be configured via ADMIN_PHONE_NUMBER environment variable."
    if normalized == "runtime":
        return "Runtime: FastAPI + Postgres session storage"
    if normalized == "about":
        return "I’m a lightweight Levanter-inspired bot running on FastAPI with Postgres storage."
    if normalized.startswith("echo "):
        return text[5:].strip() or "Nothing to echo."

    return f"You said: {text}"
