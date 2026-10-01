"""Daily: pull YouTube analytics for recent videos, find where viewers drop off,
ask Gemini what to change, and write lessons.json (read by generate_video.py)."""
import statistics
from datetime import date, datetime

from common import ROOT, STATE, LESSONS, load, save, gemini_json
from yt_auth import analytics

LOG = ROOT / "analytics_log.json"
CORE = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained"


def channel_metrics(an, vids):
    base = dict(
        ids="channel==MINE", startDate=min(v["published"] for v in vids),
        endDate=date.today().isoformat(), dimensions="video",
        filters="video==" + ",".join(v["id"] for v in vids), maxResults=200,
    )
    try:  # thumbnail CTR metrics may not be available to every channel/API version
        r = an.reports().query(metrics=CORE + ",videoThumbnailImpressions,videoThumbnailImpressionsClickRate", **base).execute()
    except Exception:
        r = an.reports().query(metrics=CORE, **base).execute()
    cols = [h["name"] for h in r["columnHeaders"]]
    return {row[0]: dict(zip(cols, row)) for row in r.get("rows", [])}


def retention_points(an, v):
    r = an.reports().query(
        ids="channel==MINE", startDate=v["published"], endDate=date.today().isoformat(),
        metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
        filters=f"video=={v['id']}",
    ).execute()
    return sorted((row[0], row[1]) for row in r.get("rows", []))


def drop_analysis(points, v):
    """Biggest retention drop (after the first 2%) and retention at ~5% (hook proxy)."""
    if len(points) < 10:
        return {}
    hook = next((w for t, w in points if t >= 0.05), None)
    best, best_t = 0, None
    for i in range(2, len(points) - 3):
        drop = points[i][1] - points[i + 3][1]
        if drop > best:
            best, best_t = drop, points[i][0]
    out = {"hook_retention_at_5pct": round(hook, 3) if hook is not None else None}
    if best_t is not None:
        secs = best_t * v["duration"]
        scene = [s for s in v["timeline"] if s["start"] <= secs][-1]
        out.update(biggest_drop_at_sec=round(secs), drop_size=round(best, 3), text_at_drop=scene["text"])
    return out


def main():
    state = load(STATE, {})
    today = date.today()
    vids = [v for v in state.get("videos", [])][-12:]
    ready = [v for v in vids if (today - datetime.fromisoformat(v["published"]).date()).days >= 2]
    if not ready:
        print("No videos old enough (analytics lag ~48h). Nothing to analyse.")
        return
    an = analytics()
    metrics = channel_metrics(an, ready)

    report = []
    for v in ready:
        m = metrics.get(v["id"])
        if not m:
            continue
        try:
            drops = drop_analysis(retention_points(an, v), v)
        except Exception as e:
            drops = {"note": f"retention unavailable: {e}"}
        report.append({"title": v["title"], "topic": v["topic"], "hook": v["hook"][:200],
                       "duration_sec": v["duration"], "published": v["published"], **m, **drops})
    if not report:
        print("No analytics rows yet.")
        return

    log = load(LOG, [])
    log.append({"date": today.isoformat(), "videos": report})
    save(LOG, log[-60:])

    views = [r.get("views", 0) for r in report]
    lessons = load(LESSONS, {})
    prompt = f"""You are a YouTube growth analyst for a faceless mystery-storytelling channel.
Below are real analytics for our recent videos (newest last). Fields: averageViewPercentage,
averageViewDuration, views, subscribersGained, optional thumbnail CTR, hook_retention_at_5pct
(share still watching 5% in), biggest_drop_at_sec + text_at_drop (where viewers left most).

Videos: {report}
Channel median views: {statistics.median(views)}
Previous lessons: {lessons.get('top_lessons', [])}

Rules: with fewer than 5 videos treat evidence as WEAK - prefer single-variable experiments
over big conclusions. Compare videos against each other, not against industry myths. Explain
patterns in hooks, titles, topic type, pacing, length and the exact scenes where viewers left.
Return ONLY JSON: {{"summary": str (3 sentences), "top_lessons": [str] (max 8, imperative and
specific, usable inside a script-writing prompt), "avoid": [str] (max 5),
"next_video_experiment": str (ONE change to test in the next video)}}"""
    result = gemini_json(prompt, temperature=0.4)

    history = lessons.get("history", [])
    history.append({"date": today.isoformat(), "summary": result["summary"]})
    save(LESSONS, {
        "updated": today.isoformat(), "summary": result["summary"],
        "top_lessons": result["top_lessons"], "avoid": result["avoid"],
        "next_video_experiment": result["next_video_experiment"], "history": history[-30:],
    })
    print(result["summary"])


if __name__ == "__main__":
    main()
