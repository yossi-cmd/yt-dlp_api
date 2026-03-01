# YouTube + Spotify Download API

תשתית API ב-**Node.js** (Express): הורדת סרטונים מ-YouTube (@distube/ytdl-core) והורדת שירים מ-Spotify (spottydl-better → YouTube Music). גישה עם API Key, פרוקסי אופציונלי, קבלת קובץ או ZIP.

## אימות (API Key)

כשמוגדר משתנה סביבה `API_KEY` ב-Railway (או locally), יש לשלוח את המזהה בכל בקשה ל-`/download`, `/download-list` ו-`/formats`:

- **Header:** `X-API-Key: <your-api-key>`
- **או:** `Authorization: Bearer <your-api-key>`

אם `API_KEY` לא מוגדר, האימות מושבת (נוח לפיתוח מקומי).

### פרוקסי כברירת מחדל (PROXY_URL)

אם מוגדר משתנה סביבה `PROXY_URL`, השרת ישתמש בו בכל הבקשות. מתאים ל־HTTP ו־SOCKS5:

```bash
PROXY_URL=http://user:password@proxy-host:port
# או
PROXY_URL=socks5://user:password@brd.superproxy.io:33335
```

## התקנה מקומית

```bash
npm install
```

## הרצה

```bash
npm start
```

השרת רץ על פורט 8000 (או משתנה `PORT`). לדוגמה: http://localhost:8000

## פריסה ב-Railway

1. חבר את הריפו ל-Railway (או העלה את הקוד).
2. Railway יזהה Node.js ויתקין dependencies מ-`package.json`.
3. פקודת ההפעלה: `node server.js` (מוגדר ב-Procfile וב-`railway.toml`). `PORT` מוגדר אוטומטית.
4. אופציונלי: הוסף `PROXY_URL` ו־`API_KEY` ב-Variables.

**אם בלוגים מופיע "uvicorn: command not found":** הפרויקט עבר ל-Node.js; Railway אולי משתמש בפקודת הפעלה ישנה. ב-Dashboard → השירות → **Settings** → **Deploy** מצא **Start Command** והגדר ל-`node server.js` (או השאר ריק כדי שישתמש ב-Procfile). אחר כך **Redeploy**.

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
- **cookies** – אופציונלי. מערך של `[{ "name": "שם_עוגיה", "value": "ערך" }]` (למשל ייצוא מ-EditThisCookie).
- **cookies_b64** – אופציונלי. קובץ cookies בפורמט Netscape (למשל מהרחבה "Get cookies.txt") מקודד ב-base64. עוזר לסרטונים עם הגבלת גיל או אימות.

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

השירות משתמש ב-**spottydl-better**: מפענח קישור Spotify, מוצא את השיר ב-YouTube Music ומוריד MP3 (כולל תגיות ואלבום). **נדרש FFmpeg** (ב-Railway מוגדר ב-`nixpacks.toml`).

- **GET /spotify/track?url=...** – מחזיר מטא־דאטה (title, artist, album, year, albumCoverURL). רק קישור **track**.
- **POST /spotify/download** – Body: `{ "url": "https://open.spotify.com/track/..." }` → מחזיר קובץ MP3.
- **POST /spotify/playlist** – Body: `{ "url": "https://open.spotify.com/playlist/..." }` או `.../album/...` → מחזיר קובץ ZIP עם כל השירים ב-MP3.

אין צורך במפתחות Spotify או YouTube; הספרייה מטפלת בכך.

### אם מתקבל 502 "Application failed to respond"

האפליקציה לא הגיבה – בדרך כלל קריסה בהפעלה או חוסר תגובה בזמן. מה לבדוק:

1. **לוגים ב-Railway:** ב-Dashboard → הפרויקט → Deployments → View Logs. חפש הודעות שגיאה (למשל בעיית טעינת `@distube/ytdl-core` או פורט).
2. **גרסת Node:** הפרויקט דורש Node 20 (`engines.node` ב-`package.json`, `.nvmrc`). Node 18 עלול לגרום ל־`File is not defined` (undici).
3. **Health check:** אחרי פריסה נסה `GET https://your-app.railway.app/health` – אם אתה מקבל `ok`, השרת עלה והבעיה בבקשה אחרת.

### אפשרויות בלי פרוקסי

1. **Cookies מהדפדפן** – עוזר לסרטונים עם הגבלת גיל או "אימות שאתה לא בוט". לא פותר חסימה לפי IP (403 מדאטהסנטר).
   - ייצוא: הרחבה [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie) או "Get cookies.txt" → ייצוא מ-youtube.com.
   - שליחה: בשדה `cookies` (מערך `[{ "name": "...", "value": "..." }]`) או `cookies_b64` (מחרוזת base64 של קובץ Netscape).
2. **הרצה במקום עם IP "רגיל"** – להריץ את השרת על מחשב ביתי או שרת עם IP שלא מזוהה כדאטהסנטר (לא Railway/AWS וכו').
3. **שימוש בשרת צד־שלישי** – שירותים שמספקים API להורדה מיוטיוב (מטפלים בפרוקסי/אימות אצלם).

לחסימת 403 מ-IP של דאטהסנטר – הפתרון האמין הוא **פרוקסי residential** (`PROXY_URL`).

### אם מתקבל "This video is not available" או 403

יוטיוב חוסם גישה מ־IP של דאטהסנטר. **פתרון מומלץ:** `PROXY_URL` עם פרוקסי residential. ספקים: [Bright Data](https://brightdata.com), [SmartProxy](https://smartproxy.com), [Oxylabs](https://oxylabs.io). **אלטרנטיבה:** שליחת **cookies** (ראו למעלה) – עוזר להגדרת גיל, לא תמיד ל-403.

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
