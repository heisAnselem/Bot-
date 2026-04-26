def generate_reply(message: str) -> str:
    text = (message or "").strip()
    normalized = text.lower()

    if not text:
        return "Send a message and I’ll respond."
    if normalized in {"hi", "hello", "hey"}:
        return "Hello 👋 I am your Levanter-style FastAPI bot."
    if normalized in {"help", "menu", "commands"}:
        return "Commands: hello, ping, about, help"
    if normalized == "ping":
        return "pong"
    if normalized == "about":
        return "I’m a lightweight Levanter-inspired bot running on FastAPI with Postgres storage."

    return f"You said: {text}"
