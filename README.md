# YouTube + Spotify Download API

תשתית API ב-**Python** (FastAPI): הורדת סרטונים מ-YouTube (yt-dlp) והורדת שירים מ-Spotify (spotdl → YouTube). גישה עם API Key, פרוקסי אופציונלי, קבלת קובץ או ZIP.

## אימות (API Key)

כשמוגדר משתנה סביבה `API_KEY` ב-Railway (או locally), יש לשלוח את המזהה בכל בקשה ל-`/download`, `/download-list`, `/formats` ולאנדפוינטים של Spotify:

- **Header:** `X-API-Key: <your-api-key>`
- **או:** `Authorization: Bearer <your-api-key>`

אם `API_KEY` לא מוגדר, האימות מושבת (נוח לפיתוח מקומי).

### פרוקסי כברירת מחדל (PROXY_URL)

אם מוגדר משתנה סביבה `PROXY_URL`, השרת ישתמש בו בכל הבקשות ל-yt-dlp (YouTube):

```bash
PROXY_URL=http://user:password@proxy-host:port
# או
PROXY_URL=socks5://user:password@host:port
```

### Spotify (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)

כדי שהאנדפוינטים של Spotify יעבדו, יש להגדיר ב-Railway Variables:

- `SPOTIFY_CLIENT_ID` – מפתח Client ID מ-[Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
- `SPOTIFY_CLIENT_SECRET` – Client Secret של האפליקציה

בלי אלה, קריאות ל-`/spotify/*` יחזירו 503.

## התקנה מקומית

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**FFmpeg** נדרש ל-spotdl (ולפורמט mp3 ב-yt-dlp). התקנה: `brew install ffmpeg` (macOS), `apt install ffmpeg` (Linux).

## הרצה

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

השרת רץ על פורט 8000 (או משתנה `PORT`). לדוגמה: http://localhost:8000

## פריסה ב-Railway

1. חבר את הריפו ל-Railway (או העלה את הקוד).
2. Railway יזהה Python (requirements.txt) ויתקין dependencies; **FFmpeg** מותקן דרך `nixpacks.toml`.
3. פקודת ההפעלה: `uvicorn main:app --host 0.0.0.0 --port $PORT` (מוגדר ב-Procfile וב-`railway.toml`).
4. הוסף Variables: `API_KEY`, אופציונלי `PROXY_URL`, ולספוטיפיי: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`.

אם Railway בוחר ב-Node במקום Python (למשל בגלל `package.json`), ב-`nixpacks.toml` מוגדר `providers = ["python"]` כדי לאכוף Python.

## Endpoints

| Method | Path | תיאור |
|--------|------|--------|
| GET | `/` | מידע על השירות (ללא אימות) |
| GET | `/formats?url=...` | רשימת פורמטים (YouTube) |
| POST | `/download` | הורדת סרטון בודד (YouTube) → קובץ |
| POST | `/download-list` | הורדת עד 20 סרטונים (YouTube) → ZIP |
| GET | `/spotify/track?url=...` | מטא־דאטה של שיר (Spotify) |
| POST | `/spotify/download` | הורדת שיר בודד (Spotify) → MP3 |
| POST | `/spotify/playlist` | הורדת פלייליסט/אלבום (Spotify) → ZIP |
| GET | `/health` | בדיקת תקינות |

### POST /download

**Body (JSON):**

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "format": "best"
}
```

- **url** – חובה. קישור לסרטון.
- **format** – אופציונלי (ברירת מחדל: `best`). ערכים: `best`, `mp4`, `mp3` (אודיו בלבד).
- **cookies** – אופציונלי. מערך של `[{ "name": "שם_עוגיה", "value": "ערך" }]`.
- **cookies_b64** – אופציונלי. קובץ cookies בפורמט Netscape (למשל מהרחבה "Get cookies.txt") מקודד ב-base64.

**תגובה:** הקובץ ישירות.

### POST /download-list

**Body (JSON):**

```json
{
  "urls": [
    "https://www.youtube.com/watch?v=ID1",
    "https://www.youtube.com/watch?v=ID2"
  ],
  "format": "best"
}
```

מחזיר קובץ ZIP עם כל הקבצים (עד 20 סרטונים).

### Spotify

השירות משתמש ב-**spotdl**: מפענח קישור Spotify, מוצא את השיר ב-YouTube ומוריד MP3 (כולל מטא־דאטה). **נדרש FFmpeg** (ב-Railway מוגדר ב-`nixpacks.toml`) ומפתחות Spotify (ראו למעלה).

- **GET /spotify/track?url=...** – מחזיר מטא־דאטה (name, artist, album וכו'). רק קישור **track**.
- **POST /spotify/download** – Body: `{ "url": "https://open.spotify.com/track/..." }` → מחזיר קובץ MP3.
- **POST /spotify/playlist** – Body: `{ "url": "https://open.spotify.com/playlist/..." }` או `.../album/...` → מחזיר קובץ ZIP עם כל השירים ב-MP3.

### אם מתקבל 502 "Application failed to respond"

1. **לוגים ב-Railway:** Dashboard → Deployments → View Logs. חפש שגיאות הפעלה (חסר FFmpeg, חסר SPOTIFY_CLIENT_ID וכו').
2. **Health check:** נסה `GET https://your-app.railway.app/health` – אם מקבלים `ok`, השרת עלה.

### אם מתקבל "This video is not available" או 403

יוטיוב חוסם גישה מ־IP של דאטהסנטר. **פתרון מומלץ:** `PROXY_URL` עם פרוקסי residential. **אלטרנטיבה:** שליחת **cookies** (ראו למעלה) – עוזר להגדרת גיל, לא תמיד ל-403.

### דוגמת קריאה

```bash
curl -X POST "https://your-app.railway.app/download" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","format":"mp4"}' \
  --output video.mp4
```

## רישיון

MIT
