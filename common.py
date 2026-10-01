import json, os, time
from pathlib import Path
import requests

ROOT = Path(__file__).parent
STATE = ROOT / "state.json"
LESSONS = ROOT / "lessons.json"
# Tried in order; the first one your key can use wins. Set GEMINI_MODEL to force one.
MODEL_CANDIDATES = [m for m in [
    os.getenv("GEMINI_MODEL"),
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
] if m]


def load(path, default):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def gemini_json(prompt, temperature=0.8):
    """Call Gemini (free tier) and return parsed JSON. Falls back across models on 404/403/429."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
    }
    errors = []
    for model in MODEL_CANDIDATES:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(4):
            r = requests.post(url, params={"key": os.environ["GEMINI_API_KEY"]}, json=body, timeout=180)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(15 * (attempt + 1))  # overloaded / rate limited: wait and retry
                continue
            break
        if r.status_code in (400, 403, 404, 429, 500, 502, 503, 504):
            errors.append(f"{model}: {r.status_code} {r.text[:150]}")
            continue
        r.raise_for_status()
        try:
            data = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            print(f"[gemini] used {model}")
            return data
        except (KeyError, ValueError) as e:
            errors.append(f"{model}: bad JSON ({e})")
    raise RuntimeError("No Gemini model worked:\n" + "\n".join(errors))
