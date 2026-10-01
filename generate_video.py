"""Free mystery-storytelling video generator.
Gemini (script) -> edge-tts (voice) -> Pollinations (images) -> ffmpeg (edit) -> Pillow (thumbnail)

Editing done automatically: alternating zoom/pan camera moves, dip fades between scenes,
color grade + vignette + film grain, burned-in captions, music with voice-ducking,
loudness normalisation, auto chapters.

Env: GEMINI_API_KEY (required), FORCE=1 (ignore 2-day gap), VOICE (edge-tts voice name)
"""
import asyncio, json, os, subprocess, sys, time, urllib.parse
from datetime import date, datetime
from pathlib import Path

import edge_tts
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from common import ROOT, STATE, LESSONS, load, save, gemini_json

OUT = ROOT / "output"
TMP = OUT / "tmp"
MUSIC = ROOT / "assets" / "music.mp3"  # optional royalty-free track (Pixabay / YT Audio Library)
VOICE = os.getenv("VOICE", "en-US-GuyNeural")
PAD = 0.4  # silence added after each scene
MOTIONS = ["in", "panr", "out", "panl"]


# ---------------------------------------------------------------- script
def should_run():
    if os.getenv("FORCE") == "1":
        return True
    last = load(STATE, {}).get("last_run")
    return not last or (date.today() - datetime.fromisoformat(last).date()).days >= 2


def make_script(state, lessons):
    prompt = f"""You write narrated YouTube scripts about real, well-documented mysteries,
told as a gripping story: a shocking hook in the first 10 seconds, rising tension, the
competing theories, and an ending that leaves an open question. Target ~8 minutes
(1100-1300 words). Only state facts you are confident are accurate; attribute theories
("investigators believe..."). Never invent quotes, names, or evidence.

Topics already covered (do not repeat): {state.get('used_topics', [])}

Lessons from our real channel analytics (apply them):
{json.dumps(lessons.get('top_lessons', []))}
Things to avoid: {json.dumps(lessons.get('avoid', []))}
Experiment to try in this video: {lessons.get('next_video_experiment', 'none')}

Return ONLY JSON:
{{"topic": str, "title": str (under 70 chars, curiosity-driven, no clickbait lies),
"description": str (2-3 sentences + list of real sources),
"tags": [str] (10-15), "thumbnail_text": str (max 4 words),
"scenes": [{{"chapter": str or null (short title, ONLY on the first scene of each of 5-7 sections),
"narration": str (40-70 words), "image_prompt": str (cinematic, moody, no text,
no real people's faces)}}]}} with 16-22 scenes."""
    return gemini_json(prompt, temperature=0.9)


# ---------------------------------------------------------------- assets
async def tts(text, path):
    await edge_tts.Communicate(text, VOICE, rate="-4%").save(str(path))


def probe_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)]
    )
    return float(out.strip())


def fetch_image(prompt, path, seed):
    q = urllib.parse.quote(prompt + ", cinematic, dark moody lighting, photorealistic")
    url = f"https://image.pollinations.ai/prompt/{q}?width=1920&height=1080&nologo=true&seed={seed}"
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                path.write_bytes(r.content)
                Image.open(path).verify()
                return
        except Exception:
            pass
        time.sleep(5 * (attempt + 1))
    Image.new("RGB", (1920, 1080), (12, 12, 18)).save(path)  # fallback dark frame


# ---------------------------------------------------------------- editing
def motion_expr(kind, frames):
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if kind == "in":
        return f"z='min(zoom+0.0007,1.25)':x='{cx}':y='{cy}'"
    if kind == "out":
        return f"z='if(eq(on,1),1.25,max(zoom-0.0007,1.0))':x='{cx}':y='{cy}'"
    if kind == "panr":
        return f"z=1.15:x='(iw-iw/zoom)*on/{frames}':y='{cy}'"
    return f"z=1.15:x='(iw-iw/zoom)*(1-on/{frames})':y='{cy}'"


def make_clip(img, audio, dur, out, kind):
    total = dur + PAD
    frames = int(total * 30) + 30
    vf = (
        "scale=2400:1350:force_original_aspect_ratio=increase,crop=2400:1350,"
        f"zoompan={motion_expr(kind, frames)}:d={frames}:s=1920x1080:fps=30,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={total - 0.25:.2f}:d=0.25,format=yuv420p"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(audio),
         "-vf", vf, "-af", f"apad=pad_dur={PAD}", "-t", f"{total:.2f}", "-r", "30",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out)],
        check=True, capture_output=True,
    )


def ass_time(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def caption_events(text, start, dur, per=5):
    words = text.replace("{", "(").replace("}", ")").split()
    chunks = [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
    total = sum(len(c) for c in chunks) or 1
    t, events = start, []
    for c in chunks:
        d = dur * len(c) / total
        events.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d)},Main,,0,0,0,,{c}")
        t += d
    return events


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Main,DejaVu Sans,66,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,2,120,120,90,1

[Events]
Format: Layer,Start,End,Style,Name,Effect,Text
"""


def final_render(joined, out):
    """Color grade + grain + vignette + captions; duck music under the voice; normalise loudness."""
    vfx = ("[0:v]eq=contrast=1.08:saturation=0.85:brightness=-0.02,vignette=PI/5,"
           "noise=alls=5:allf=t,subtitles=captions.ass[v]")
    if MUSIC.exists():
        afx = ("[0:a]asplit=2[vo][sc];[1:a]volume=0.35[m];"
               "[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=500[duck];"
               "[vo][duck]amix=inputs=2:duration=first:dropout_transition=0,"
               "loudnorm=I=-16:TP=-1.5:LRA=11[a]")
        inputs = ["-i", str(joined), "-stream_loop", "-1", "-i", str(MUSIC)]
    else:
        afx = "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]"
        inputs = ["-i", str(joined)]
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", f"{vfx};{afx}", "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(out)],
        check=True, capture_output=True, cwd=TMP,  # cwd so 'captions.ass' resolves without escaping
    )


def thumbnail(first_img, text, out):
    img = Image.open(first_img).convert("RGB").resize((1280, 720))
    img = ImageEnhance.Contrast(ImageEnhance.Brightness(img).enhance(0.6)).enhance(1.25)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 130)
    except OSError:
        font = ImageFont.load_default()
    lines, cur = [], ""
    for w in text.upper().split():
        if len(cur + w) > 12 and cur:
            lines.append(cur.strip()); cur = ""
        cur += w + " "
    lines.append(cur.strip())
    y = 360 - 75 * len(lines)
    for line in lines:
        d.text((60, y), line, font=font, fill="yellow", stroke_width=8, stroke_fill="black")
        y += 150
    img.save(out, quality=92)


def fmt_ts(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapter_text(timeline):
    marks = [(t["start"], t["chapter"]) for t in timeline if t.get("chapter")]
    if not marks or marks[0][0] > 0:
        marks.insert(0, (0, "Intro"))
    marks[0] = (0, marks[0][1])
    kept = []
    for t, name in marks:
        if not kept or t - kept[-1][0] >= 10:
            kept.append((t, name))
    if len(kept) < 3:
        return ""
    return "\n".join(f"{fmt_ts(t)} {name}" for t, name in kept)


# ---------------------------------------------------------------- main
def main():
    if not should_run():
        print("Posted less than 2 days ago; skipping.")
        return
    OUT.mkdir(exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    state, lessons = load(STATE, {}), load(LESSONS, {})

    script = make_script(state, lessons)
    scenes = script["scenes"]
    print("Topic:", script["topic"], f"({len(scenes)} scenes)")

    clips, timeline, events, cursor = [], [], [], 0.0
    for i, sc in enumerate(scenes):
        a, im, c = TMP / f"a{i}.mp3", TMP / f"i{i}.jpg", TMP / f"c{i}.mp4"
        asyncio.run(tts(sc["narration"], a))
        fetch_image(sc["image_prompt"], im, seed=i + 1)
        dur = probe_duration(a)
        make_clip(im, a, dur, c, MOTIONS[i % len(MOTIONS)])
        clips.append(c)
        timeline.append({"start": round(cursor, 1), "chapter": sc.get("chapter"), "text": sc["narration"][:140]})
        events += caption_events(sc["narration"], cursor, dur)
        cursor += dur + PAD
        print(f"scene {i + 1}/{len(scenes)} done")

    (TMP / "captions.ass").write_text(ASS_HEADER + "\n".join(events) + "\n", encoding="utf-8")
    (TMP / "list.txt").write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = TMP / "joined.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(TMP / "list.txt"),
                    "-c", "copy", str(joined)], check=True, capture_output=True)

    final = OUT / "video.mp4"
    final_render(joined, final)
    thumbnail(TMP / "i0.jpg", script["thumbnail_text"], OUT / "thumbnail.jpg")

    chapters = chapter_text(timeline)
    description = script["description"] + (f"\n\nChapters:\n{chapters}" if chapters else "")
    description += "\n\nNarration and images are AI-generated."
    save(OUT / "meta.json", {
        "title": script["title"], "description": description, "tags": script["tags"],
        "topic": script["topic"], "duration": round(probe_duration(final), 1),
        "hook": scenes[0]["narration"], "timeline": timeline,
    })

    state["last_run"] = date.today().isoformat()
    state.setdefault("used_topics", []).append(script["topic"])
    save(STATE, state)
    print("Done:", final)


if __name__ == "__main__":
    sys.exit(main())
