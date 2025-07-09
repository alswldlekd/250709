import json
import os
from datetime import datetime

CACHE_FILE = "alert_cache.json"

def load_alert_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_alert_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_alert_cache(keyword, status, details):
    cache = load_alert_cache()
    cache[keyword] = {
        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": status,
        "details": details
    }
    save_alert_cache(cache)
