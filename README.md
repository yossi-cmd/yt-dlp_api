# YouTube Download API

תשתית API להורדת סרטונים מ-YouTube ב-**Node.js** (Express + @distube/ytdl-core): גישה עם מזהה (API Key), פרוקסי אופציונלי מהסביבה, וקבלת הקובץ ישירות בתגובה. מתאים לפריסה ב-Railway.

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
3. פקודת ההפעלה: `node server.js` (מוגדר ב-Procfile). `PORT` מוגדר אוטומטית.
4. אופציונלי: הוסף `PROXY_URL` ו־`API_KEY` ב-Variables.

## Endpoints

| Method | Path | תיאור |
|--------|------|--------|
| GET | `/` | מידע על השירות (ללא אימות) |
| GET | `/formats?url=...` | רשימת פורמטים זמינים לסרטון |
| POST | `/download` | הורדת סרטון בודד → **מחזיר קובץ** |
| POST | `/download-list` | הורדת עד 20 סרטונים → **קובץ ZIP** |

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

### אם מתקבל 502 "Application failed to respond"

האפליקציה לא הגיבה – בדרך כלל קריסה בהפעלה או חוסר תגובה בזמן. מה לבדוק:

1. **לוגים ב-Railway:** ב-Dashboard → הפרויקט → Deployments → View Logs. חפש הודעות שגיאה (למשל בעיית טעינת `@distube/ytdl-core` או פורט).
2. **גרסת Node:** הפרויקט מוגדר ל-Node 18 (`engines.node` ב-`package.json`). אם Railway מריץ גרסה אחרת, ייתכן שתקבל 502.
3. **Health check:** אחרי פריסה נסה `GET https://your-app.railway.app/health` – אם אתה מקבל `ok`, השרת עלה והבעיה בבקשה אחרת.

### אם מתקבל "This video is not available"

יוטיוב עלול לחסום גישה מ־IP של דאטהסנטר. **פתרון:** להגדיר `PROXY_URL` עם פרוקסי residential (או SOCKS5). ספקים: [Bright Data](https://brightdata.com), [SmartProxy](https://smartproxy.com), [Oxylabs](https://oxylabs.io).

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
