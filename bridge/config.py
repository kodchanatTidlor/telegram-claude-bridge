import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    allowed_chat_id: int
    poll_timeout: int
    store_path: Path
    flag_path: Path
    pid_path: Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def load_config() -> Config:
    _load_dotenv(BASE_DIR / ".env")
    token = os.environ.get("BOT_TOKEN")
    chat = os.environ.get("ALLOWED_CHAT_ID")
    if not token:
        raise ValueError("BOT_TOKEN missing")
    if not chat:
        raise ValueError("ALLOWED_CHAT_ID missing")
    return Config(
        bot_token=token,
        allowed_chat_id=int(chat),
        poll_timeout=int(os.environ.get("POLL_TIMEOUT", "50")),
        store_path=Path(os.environ.get("STORE_PATH", BASE_DIR / ".store.json")),
        flag_path=BASE_DIR / ".enabled",
        pid_path=BASE_DIR / ".listener.pid",
    )


def is_allowed(cfg: Config, chat_id: int) -> bool:
    return chat_id == cfg.allowed_chat_id
