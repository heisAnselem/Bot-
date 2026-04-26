from datetime import datetime
import platform
import time

APP_START_MONOTONIC = time.monotonic()

MENU_SECTIONS: list[tuple[str, list[str]]] = [
    ("ᴀɪ", ["BING", "DALL", "GEMINI", "GPT", "GROQ", "UPSCALE"]),
    (
        "ᴀᴜᴅɪᴏ",
        [
            "AVEC",
            "BASS",
            "BLACK",
            "BLOWN",
            "CUT",
            "DEEP",
            "EARRAPE",
            "FAST",
            "FAT",
            "HISTO",
            "LOW",
            "NIGHTCORE",
            "PITCH",
            "ROBOT",
            "SLOW",
            "SMOOTH",
            "TREBLE",
            "TUPAI",
            "VECTOR",
        ],
    ),
    ("ᴀᴜᴛᴏʀᴇᴘʟʏ", ["FILTER", "GFILTER", "GSTOP", "PFILTER", "PSTOP", "STOP"]),
    ("ʙᴏᴛ", ["GAUTH", "GUPLOAD", "REMINDER", "TASK", "TOG", "UPDATE", "UPDATE NOW"]),
    ("ʙᴜᴅɢᴇᴛ", ["DELBUDGET", "EXPENSE", "INCOME", "SUMMARY"]),
    ("ᴅᴏᴄᴜᴍᴇɴᴛ", ["PAGE", "PDF"]),
    (
        "ᴅᴏᴡɴʟᴏᴀᴅ",
        [
            "APK",
            "FB",
            "FULLSS",
            "INSTA",
            "MEDIAFIRE",
            "PINTEREST",
            "PLAY",
            "REDDIT",
            "SONG",
            "SPOTIFY",
            "SS",
            "STORY",
            "TIKTOK",
            "TWITTER",
            "UPLOAD",
            "VIDEO",
            "YTA",
            "YTV",
        ],
    ),
    (
        "ᴇᴅɪᴛᴏʀ",
        [
            "BLOODY",
            "BOKEH",
            "CARTOON",
            "COLOR",
            "DARK",
            "DEMON",
            "ENHANCE",
            "GANDM",
            "HORNED",
            "KISS",
            "LOOK",
            "MAKEUP",
            "PENCIL",
            "SKETCH",
            "SKULL",
            "WANTED",
            "ZOMBIE",
        ],
    ),
    ("ɢᴀᴍᴇ", ["TICTACTOE", "WCG", "WRG"]),
    (
        "ɢʀᴏᴜᴘ",
        [
            "ADD",
            "AMUTE",
            "ANTIFAKE",
            "ANTIGM",
            "ANTILINK",
            "ANTISPAM",
            "ANTIWORD",
            "AUNMUTE",
            "COMMON",
            "DEMOTE",
            "GINFO",
            "GOODBYE",
            "GPP",
            "GSTATUS",
            "INACTIVE",
            "INVITE",
            "JOIN",
            "KICK",
            "MSGS",
            "MUTE",
            "PDM",
            "PROMOTE",
            "RESET",
            "REVOKE",
            "TAG",
            "UNMUTE",
            "VOTE",
            "WARN",
            "WELCOME",
        ],
    ),
    ("ʟᴏɢɪᴀ", ["OPE", "YAMI", "ZUSHI"]),
    (
        "ᴍɪsᴄ",
        [
            "AFK",
            "ALIVE",
            "AVM",
            "CALC",
            "CREACT",
            "DELCMD",
            "FANCY",
            "FORWARD",
            "GETCMD",
            "LYDIA",
            "MENTION",
            "MFORWARD",
            "NEWS",
            "PING",
            "QR",
            "REACT",
            "REBOOT",
            "RMBG",
            "SAVE",
            "SETCMD",
            "TTS",
            "URL",
            "WHOIS",
        ],
    ),
    ("ᴘᴇʀsᴏɴᴀʟ", ["DELGREET", "GETGREET", "SETGREET"]),
    ("ᴘʟᴜɢɪɴ", ["PLUGIN", "REMOVE"]),
    ("sᴄʜᴇᴅᴜʟᴇ", ["DELSCHEDULE", "GETSCHEDULE", "SETSCHEDULE"]),
    ("sᴇᴀʀᴄʜ", ["EMIX", "EMOJI", "FIND", "IG", "IMG", "ISON", "JEAN", "MOVIE", "TIME", "TRT", "WEATHER", "YTS"]),
    ("sᴛɪᴄᴋᴇʀ", ["CIRCLE", "EXIF", "MP4", "PHOTO", "STICKER", "TAKE", "TG"]),
    (
        "ᴛᴇxᴛᴍᴀᴋᴇʀ",
        [
            "3D",
            "ANGEL",
            "AVENGER",
            "BLUB",
            "BPINK",
            "CAT",
            "GLITCH",
            "GLITTER",
            "GRAFFITI",
            "HACKER",
            "LIGHT",
            "MARVEL",
            "NEON",
            "SCI",
            "SIGN",
            "TATTOO",
            "WATERCOLOR",
        ],
    ),
    ("ᴜsᴇʀ", ["BLOCK", "FULLPP", "GJID", "JID", "LEFT", "PP", "UNBLOCK"]),
    ("ᴠᴀʀs", ["ALLVAR", "DELSUDO", "DELVAR", "GETSUDO", "GETVAR", "SETSUDO", "SETVAR"]),
    ("ᴠɪᴅᴇᴏ", ["COMPRESS", "CROP", "MERGE", "MP3", "REVERSE", "ROTATE", "TRIM"]),
    ("ᴡʜᴀᴛsᴀᴘᴘ", ["CALL", "CAPTION", "CLEAR", "DELETE", "DLT", "DOC", "ONLINE", "POLL", "READ", "SCSTATUS", "SETSTATUS", "STATUS", "VV"]),
]

SUPPORTED_COMMANDS = {"ping", "alive", "status", "about", "owner", "runtime", "echo", "menu", "help", "commands"}


def _display_user(sender: str) -> str:
    base = (sender or "").strip()
    if not base:
        return "User"
    if "@" in base:
        base = base.split("@", 1)[0]
    return base


def _format_uptime() -> str:
    elapsed = int(time.monotonic() - APP_START_MONOTONIC)
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _menu_header(prefix: str, sender: str, version: str, plugins: int) -> str:
    now = datetime.now()
    user = _display_user(sender)
    ram = _ram_usage()
    return (
        "╭═══ LEVANTER ═══⊷\n"
        "┃❃╭──────────────\n"
        f"┃❃│ Prefix : {prefix}\n"
        f"┃❃│ User : {user}\n"
        f"┃❃│ Time : {now.strftime('%I:%M %p')}\n"
        f"┃❃│ Day : {now.strftime('%A')}\n"
        f"┃❃│ Date : {now.month}/{now.day}/{now.year}\n"
        f"┃❃│ Version : {version}\n"
        f"┃❃│ Plugins : {plugins}\n"
        f"┃❃│ Ram : {ram}\n"
        f"┃❃│ Uptime : {_format_uptime()}\n"
        f"┃❃│ Platform : {platform.system()} {platform.machine()}\n"
        "┃❃╰───────────────\n"
        "╰═════════════════⊷"
    )


def _ram_usage() -> str:
    try:
        mem_total_kb = 0
        mem_available_kb = 0
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available_kb = int(line.split()[1])
                if mem_total_kb and mem_available_kb:
                    break

        if not mem_total_kb:
            return "unknown"
        used_kb = max(mem_total_kb - mem_available_kb, 0)
        return f"{used_kb // 1024}/{mem_total_kb // 1024}MB"
    except OSError:
        return "unknown"


def _menu_sections() -> str:
    blocks: list[str] = []
    for name, commands in MENU_SECTIONS:
        line = " │ ".join(commands)
        blocks.append(f"╭─❏ {name} ❏\n│ {line}\n╰─────────────────")
    return "\n".join(blocks)


def _full_menu(prefix: str, sender: str, version: str, plugins: int) -> str:
    return f"{_menu_header(prefix, sender, version, plugins)}\n{_menu_sections()}"


def generate_reply(message: str, sender: str, prefix: str, version: str, plugins: int) -> str:
    text = (message or "").strip()
    if not text:
        return f"Use {prefix}menu to open commands."

    if not text.startswith(prefix):
        return f"WhatsApp command mode is enabled. Use {prefix}menu."

    command_line = text[len(prefix) :].strip()
    if not command_line:
        return f"Use {prefix}menu to open commands."

    command, _, args = command_line.partition(" ")
    normalized = command.lower().strip()

    if normalized in {"menu", "help", "commands"}:
        return _full_menu(prefix=prefix, sender=sender, version=version, plugins=plugins)
    if normalized in {"hi", "hello", "hey"}:
        return "Hello 👋 I am your Levanter-style WhatsApp bot."
    if normalized == "ping":
        return "pong"
    if normalized in {"alive", "status"}:
        return "I am alive and running ✅"
    if normalized == "owner":
        return "Owner can be configured via ADMIN_PHONE_NUMBER environment variable."
    if normalized == "runtime":
        return "Runtime: FastAPI + Postgres + WhatsApp session storage"
    if normalized == "about":
        return "I’m a Levanter-style WhatsApp-only bot backend running on FastAPI."
    if normalized == "echo":
        return args.strip() or "Nothing to echo."
    if normalized in SUPPORTED_COMMANDS:
        return f"{prefix}{normalized} is available."

    return f"Unknown command. Use {prefix}menu."
