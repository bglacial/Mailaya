from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
    google_token_path: Path
    google_client_id: str
    google_client_secret: str
    laya_backend: str
    laya_model: str
    laya_dtype: str
    max_emails_per_run: int
    host: str
    port: int

    @property
    def is_apple_silicon(self) -> bool:
        return platform.system() == "Darwin" and platform.machine() == "arm64"

    @property
    def gmail_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


def get_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    data_dir = Path(os.getenv("LAYA_MAIL_DATA_DIR", PROJECT_ROOT / "data")).resolve()
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        database_path=data_dir / "laya-mail.sqlite3",
        google_token_path=data_dir / "google-token.json",
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        laya_backend=os.getenv("LAYA_BACKEND", "auto").strip().lower(),
        laya_model=os.getenv("LAYA_MODEL", "aac6fef/laya-multilingual-mlx").strip(),
        laya_dtype=os.getenv("LAYA_DTYPE", "float16").strip(),
        max_emails_per_run=max(1, min(int(os.getenv("MAX_EMAILS_PER_RUN", "500")), 5000)),
        host=os.getenv("HOST", "127.0.0.1").strip(),
        port=int(os.getenv("PORT", "8000")),
    )
