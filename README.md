# YouTube Download API

תשתית API להורדת סרטונים מ-YouTube באמצעות **pytubefix**: גישה עם מזהה (API Key), פרוקסי אופציונלי מהסביבה, וקבלת הקובץ ישירות בתגובה. מתאים לפריסה ב-Railway.

## אימות (API Key)

כשמוגדר משתנה סביבה `API_KEY` ב-Railway (או locally), יש לשלוח את המזהה בכל בקשה ל-`/download`, `/download-list` ו-`/formats`:

- **Header:** `X-API-Key: <your-api-key>`
- **או:** `Authorization: Bearer <your-api-key>`

אם `API_KEY` לא מוגדר, האימות מושבת (נוח לפיתוח מקומי).

### פרוקסי כברירת מחדל (PROXY_URL)

אם מוגדר משתנה סביבה `PROXY_URL`, השרת ישתמש בו בכל הבקשות (כולל `/formats`). מתאים ל־HTTP ו־SOCKS5:

```bash
# HTTP
PROXY_URL=http://user:password@proxy-host:port

# SOCKS5 (למשל Bright Data – לפעמים עובד טוב יותר מ־HTTP)
PROXY_URL=socks5://user:password@brd.superproxy.io:33335
```

דוגמה עם Bright Data (ממיר מ־curl):
- `PROXY_URL=http://brd-customer-XXX-zone-datacenter_proxy1:YYY@brd.superproxy.io:33335`
- או SOCKS5 אם זמין: `PROXY_URL=socks5://...`

## התקנה מקומית

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## הרצה

```bash
python main.py
# או
uvicorn main:app --reload --port 8000
```

API זמין ב-http://localhost:8000, תיעוד ב-http://localhost:8000/docs.

## פריסה ב-Railway

1. חבר את הריפו ל-Railway (או העלה את הקוד).
2. Railway יזהה Python ויתקין את ה-dependencies מ-`requirements.txt`.
3. פקודת ההפעלה מוגדרת ב-`Procfile`: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
4. אופציונלי: הוסף `PROXY_URL` (ו־`API_KEY`) ב-Variables.

## Endpoints

| Method | Path | תיאור |
|--------|------|--------|
| GET | `/` | מידע על השירות (ללא אימות) |
| GET | `/formats?url=...` | רשימת סטרימים/פורמטים זמינים לסרטון |
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
- **format** – אופציונלי (ברירת מחדל: `best`). ערכים: `best` (הרזולוציה הגבוהה ביותר), `mp4`, `mp3` (אודיו בלבד – קובץ m4a/webm).
- **options** – שמור לשימוש עתידי (לא בשימוש כרגע).
- **cookies_b64** – לא בשימוש עם pytubefix (נשמר לתאימות API).

**תגובה:** הקובץ ישירות (גוף התגובה = הקובץ).

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

### אם מתקבל "This video is not available"

יוטיוב עלול לחסום גישה מ־IP של דאטהסנטר (Railway, AWS וכו'). **פתרון:** להגדיר `PROXY_URL` עם פרוקסי **residential** (או SOCKS5 אם הספק תומך). ספקים מומלצים: [Bright Data](https://brightdata.com), [SmartProxy](https://smartproxy.com), [Oxylabs](https://oxylabs.io). עם פרוקסי HTTP ש־403, לנסות אותו כ־SOCKS5 אם הזמין.

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
