"""Upload output/video.mp4 + thumbnail to YouTube and record it in state.json for analytics."""
import os
from datetime import date

from googleapiclient.http import MediaFileUpload

from common import ROOT, STATE, load, save
from yt_auth import youtube

OUT = ROOT / "output"


def main():
    video, thumb, meta_path = OUT / "video.mp4", OUT / "thumbnail.jpg", OUT / "meta.json"
    if not video.exists():
        print("No new video to upload.")
        return
    if not os.getenv("YT_REFRESH_TOKEN"):
        print("YouTube secrets not set; skipping upload (video is in the run's artifacts).")
        return
    meta = load(meta_path, {})
    yt = youtube()
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4900],
            "tags": [t.replace("<", "").replace(">", "") for t in meta["tags"]][:15],
            "categoryId": "24",  # Entertainment
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": os.getenv("PRIVACY", "public"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # AI-generated visuals/voice disclosure
        },
    }
    req = yt.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True),
    )
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"uploaded {int(status.progress() * 100)}%")
    vid = resp["id"]
    print("Video ID:", vid, "https://youtu.be/" + vid)

    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
    except Exception as e:  # needs a phone-verified channel
        print("Thumbnail not set:", e)

    state = load(STATE, {})
    state.setdefault("videos", []).append({
        "id": vid, "title": meta["title"], "topic": meta["topic"],
        "published": date.today().isoformat(), "duration": meta["duration"],
        "hook": meta["hook"], "timeline": meta["timeline"],
    })
    save(STATE, state)


if __name__ == "__main__":
    main()
