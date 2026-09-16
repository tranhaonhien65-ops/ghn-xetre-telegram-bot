import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "ghn_token.txt"
STATE_FILE = BASE_DIR / "bot_state.json"
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "BOT_TOKEN": "8806856427:AAHO34in208GSDHwgrH8Ena8sJhfEnc-kdw",
    "GROUP_ID": -5311462943,
    "POLL_INTERVAL_SECONDS": 60,
    "DELAY_THRESHOLD_MINUTES": 1,
    "SILENT_ALERTS": False
}

def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception as e:
            print(f"[WARN] Error loading config.json: {e}")
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Error saving config.json: {e}")

DEFAULT_GHN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0eXAiOiJjb29yZGluYXRvciIsImNpZCI6NzYzMCwiaGlkIjoiTFRORyIsIm5vYyI6IlRy4bqnbiBI4bqhbyBOaGnDqm4iLCJwb2MiOiIwOTQ5MDkwNDEwIiwiZXhwIjoxNzg5NjkyOTEyfQ.yiH2u3BbqGvGwzDD8TOLWWOhPztMuUoAHn9bwPDn91A"

def get_ghn_token() -> str:
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                t = f.read().strip()
                if t:
                    return t
        except Exception:
            pass
    return DEFAULT_GHN_TOKEN

def save_ghn_token(new_token: str):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(new_token.strip())
