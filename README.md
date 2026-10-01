# Free YouTube mystery-story automation

Every 2 days: Gemini writes a story -> edge-tts voices it -> AI images -> ffmpeg edits
(camera moves, fades, grade, grain, captions, music ducking, chapters) -> uploads to YouTube.
Every day: analytics are pulled, retention drop-offs are found, Gemini writes `lessons.json`,
and the next script prompt uses those lessons.

## Setup (all free)
1. **Gemini key:** aistudio.google.com -> Get API key. Add as repo secret `GEMINI_API_KEY`.
2. **Google Cloud project:** console.cloud.google.com -> new project -> enable
   "YouTube Data API v3" and "YouTube Analytics API".
3. **OAuth consent screen:** External. Add yourself as a test user, then click
   **Publish app** (In production). Otherwise refresh tokens expire after 7 days.
4. **Credentials:** Create OAuth client ID -> type *Desktop app* -> download as `client_secret.json`
   into this folder.
5. On your computer: `pip install -r requirements.txt && python get_refresh_token.py`
   Log in with the channel's Google account. Add the 3 printed values as repo secrets
   (`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`).
6. Optional: put a royalty-free track at `assets/music.mp3`.
7. Push to GitHub (public repo = unlimited free Action minutes), then run
   **Actions -> make-and-upload-video -> Run workflow** with the repo set up.

## Known catches
- Unaudited API projects: uploads are forced **private** until you pass YouTube's API audit
  (search "YouTube API Services audit form"). Until then, set `PRIVACY: private` and publish
  from Studio, or download the artifact and upload manually.
- Thumbnail upload needs a phone-verified channel.
- Analytics lag ~48h, so each video is first analysed on day 2-3.
- Fully automated channels can be demonetised as mass-produced content. Watch your videos.
