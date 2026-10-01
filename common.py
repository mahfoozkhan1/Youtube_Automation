import json, os, time
from pathlib import Path
import requests

ROOT = Path(__file__).parent
STATE = ROOT / "state.json"
LESSONS = ROOT / "lessons.json"
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def load(path, default):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def gemini_json(prompt, temperature=0.8):
    """Call Gemini (free tier) and return parsed JSON. Retries on rate limits."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
    }
    last = None
    for attempt in range(4):
        r = requests.post(url, params={"key": os.environ["GEMINI_API_KEY"]}, json=body, timeout=180)
        if r.status_code in (429, 500, 503):
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        try:
            return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, ValueError) as e:
            last = e
    raise RuntimeError(f"Gemini failed: {last}")
