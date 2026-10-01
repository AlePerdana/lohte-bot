"""Utility: load config (.env + config.json + state.json), logging, retry."""

import os
import json
import logging
import time
from pathlib import Path
from functools import wraps
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
STATE_PATH = BASE_DIR / "config" / "state.json"
ENV_PATH = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"

# Load .env (credential & preference saja)
load_dotenv(ENV_PATH)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def default_config() -> dict:
    """Config default untuk pengguna baru (saat config.json belum ada)."""
    return {
        "tahun": 2026,
        "semester": 1,
        "jadwal_kirim": "06:30",
        "poll_interval": 30,
        "presensi_interval": [5, 60],
    }


def default_state() -> dict:
    """State default (kosong) untuk pengguna baru."""
    return {
        "token": "",
        "refresh_token": "",
        "mahasiswa": {"nomor": None, "nipnrp": "", "nama": ""},
        "kuliah": [],
        "tahun": 2026,
        "semester": 1,
    }


def _write_json(path: Path, data: dict):
    path.parent.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_state() -> dict:
    """State: token, refresh_token, identitas, daftar kuliah.

    Sumber: config/state.json (auto-generate default jika belum ada).
    """
    state = _read_json(STATE_PATH)
    if not state:
        state = default_state()
        _write_json(STATE_PATH, state)
        log_state = logging.getLogger("utils")
        log_state.info("state.json belum ada → dibuat default di %s", STATE_PATH)
    # pastikan semua key ada
    for k, v in default_state().items():
        state.setdefault(k, v)
    return state


def save_state(state: dict):
    _write_json(STATE_PATH, state)


def load_config() -> dict:
    """Gabungan: config.json (app config) + state.json (runtime) + .env (prefs).

    Prioritas: .env > state.json > config.json > default.
    config.json auto-generate dari default jika belum ada.
    """
    cfg = _read_json(CONFIG_PATH)
    if not cfg:
        cfg = default_config()
        _write_json(CONFIG_PATH, cfg)
        logging.getLogger("utils").info("config.json belum ada → dibuat default di %s", CONFIG_PATH)

    state = load_state()

    # App config defaults
    for k, v in default_config().items():
        cfg.setdefault(k, v)
    cfg.setdefault("whatsapp", {"enabled": False, "target": "", "provider": "callmebot", "apikey": ""})

    # State override (token, identitas, kuliah)
    cfg["token"] = state.get("token", "")
    cfg["refresh_token"] = state.get("refresh_token", "")
    cfg["mahasiswa"] = state.get("mahasiswa", {})
    cfg["kuliah"] = state.get("kuliah", [])
    if state.get("tahun"):
        cfg["tahun"] = state["tahun"]
    if state.get("semester"):
        cfg["semester"] = state["semester"]

    # .env overrides (preferences)
    if os.getenv("ETHOL_LOGIN_USERNAME"):
        cfg["login_username"] = os.environ["ETHOL_LOGIN_USERNAME"]
    if os.getenv("ETHOL_LOGIN_PASSWORD"):
        cfg["login_password"] = os.environ["ETHOL_LOGIN_PASSWORD"]
    if os.getenv("PRESENSI_INTERVAL"):
        lo, hi = os.environ["PRESENSI_INTERVAL"].split(",")
        cfg["presensi_interval"] = [int(lo), int(hi)]

    # WhatsApp dari .env
    if os.getenv("WA_ENABLED") is not None:
        cfg["whatsapp"]["enabled"] = os.environ["WA_ENABLED"].lower() == "true"
    if os.getenv("WA_TARGET"):
        cfg["whatsapp"]["target"] = os.environ["WA_TARGET"]
    if os.getenv("WA_PROVIDER"):
        cfg["whatsapp"]["provider"] = os.environ["WA_PROVIDER"]
    if os.getenv("WA_APIKEY"):
        cfg["whatsapp"]["apikey"] = os.environ["WA_APIKEY"]

    return cfg


# ---------- logging ----------

def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "bot.log"),
            logging.StreamHandler(),
        ],
    )


# ---------- retry ----------

def retry(times: int = 3, delay: float = 2.0, exceptions=(Exception,)):
    """Decorator: retry dengan delay eksponensial."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last = None
            for i in range(times):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last = e
                    wait = delay * (2 ** i)
                    logging.getLogger("retry").warning(
                        "%s failed (%s), retry %d/%d in %.1fs",
                        fn.__name__, e, i + 1, times, wait,
                    )
                    time.sleep(wait)
            raise last
        return wrapper
    return decorator


def random_interval(lo: int = 5, hi: int = 60) -> float:
    import random
    return random.uniform(lo, hi)