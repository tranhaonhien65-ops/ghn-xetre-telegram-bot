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

# In-memory token cache (survives within a single Render session)
_token_cache: str = ""

def is_token_valid(token: str) -> bool:
    if not token or len(token) < 30:
        return False
    try:
        import base64, time
        parts = token.split('.')
        if len(parts) >= 2:
            padded = parts[1] + '=' * (-len(parts[1]) % 4)
            payload_json = json.loads(base64.b64decode(padded).decode('utf-8'))
            exp = payload_json.get('exp', 0)
            return time.time() < exp
    except Exception:
        pass
    return False

def get_ghn_token() -> str:
    global _token_cache
    # 1. In-memory cache (updated live by Tampermonkey webhook)
    if _token_cache and is_token_valid(_token_cache):
        return _token_cache
    # 2. Token file (written by webhook, ephemeral on Render)
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                t = f.read().strip()
                if t and is_token_valid(t):
                    _token_cache = t
                    return t
        except Exception:
            pass
    # 3. Environment variable GHN_TOKEN (persistent on Render across restarts)
    env_token = os.environ.get("GHN_TOKEN", "").strip()
    if env_token and is_token_valid(env_token):
        _token_cache = env_token
        return env_token
    # 4. Fallback (return cache if exists, otherwise env or default)
    return _token_cache or env_token or DEFAULT_GHN_TOKEN


def save_ghn_token(new_token: str):
    global _token_cache
    new_token = new_token.strip()
    _token_cache = new_token
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(new_token)
    except Exception as e:
        print(f"[WARN] Cannot write token file: {e}")
