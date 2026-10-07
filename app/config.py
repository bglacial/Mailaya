from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAYA_MODEL = "convaiinnovations/laya-multilingual"
JULIA_MODEL = "SupersonicLabs/Julia-1"
JULIA_REVISION = "a85b127321d580d65176c89ced8273f305745d85"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    database_path: Path
    laya_backend: str
    laya_model: str
    max_emails_per_run: int
    host: str
    port: int
    julia_model: str = JULIA_MODEL
    julia_revision: str | None = JULIA_REVISION
    julia_device: str = "cpu"
    secure_cookies: bool = False
    laya_device: str = "cpu"

    @property
    def is_apple_silicon(self) -> bool:
        return platform.system() == "Darwin" and platform.machine() == "arm64"



def get_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    data_dir = Path(os.getenv("LAYA_MAIL_DATA_DIR", PROJECT_ROOT / "data")).resolve()
    julia_model = os.getenv("JULIA_MODEL", JULIA_MODEL).strip()
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        database_path=data_dir / "laya-mail.sqlite3",
        laya_backend=os.getenv("LAYA_BACKEND", "auto").strip().lower(),
        laya_model=os.getenv("LAYA_MODEL", LAYA_MODEL).strip(),
        max_emails_per_run=max(1, min(int(os.getenv("MAX_EMAILS_PER_RUN", "500")), 5000)),
        host=os.getenv("HOST", "127.0.0.1").strip(),
        port=int(os.getenv("PORT", "8000")),
        julia_model=julia_model,
        julia_revision=os.getenv("JULIA_REVISION", JULIA_REVISION if julia_model == JULIA_MODEL else "").strip() or None,
        julia_device=os.getenv("JULIA_DEVICE", "cpu").strip().lower(),
        laya_device=os.getenv("LAYA_DEVICE", "cpu").strip().lower(),
        secure_cookies=os.getenv("MAILAYA_SECURE_COOKIES", "false").lower() == "true",
    )
