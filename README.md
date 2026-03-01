# YouTube Download API

תשתית API להורדת סרטונים מ-YouTube: גישה עם מזהה (API Key), העברת כל הפרמטרים בבקשה, וקבלת הקובץ ישירות בתגובה. מתאים לפריסה ב-Railway.

## אימות (API Key)

כשמוגדר משתנה סביבה `API_KEY` ב-Railway (או locally), יש לשלוח את המזהה בכל בקשה ל-`/download`, `/download-list` ו-`/formats`:

- **Header:** `X-API-Key: <your-api-key>`
- **או:** `Authorization: Bearer <your-api-key>`

אם `API_KEY` לא מוגדר, האימות מושבת (נוח לפיתוח מקומי).

## התקנה מקומית

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

להמרת וידאו לאודיו (MP3 וכו') נדרש [FFmpeg](https://ffmpeg.org/) מותקן במערכת.

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

אם תרצה להמיר ל-MP3 ב-Railway, הוסף Buildpack של FFmpeg או השתמש ב-[Nixpacks](https://nixpacks.com/) עם `nixpacks.toml` שמתקין FFmpeg.

## Endpoints

| Method | Path | תיאור |
|--------|------|--------|
| GET | `/` | מידע על השירות (ללא אימות) |
| GET | `/formats?url=...` | רשימת פורמטים זמינים לסרטון |
| POST | `/download` | העברת פרמטרים בבקשה → **מחזיר את הקובץ ישירות** |
| POST | `/download-list` | כמה סרטונים → **מחזיר קובץ ZIP** |

כל הפרמטרים מועברים ב-body (ו־`options` לפרמטרים נוספים של yt-dlp); התגובה היא הקובץ עצמו (או ZIP).

### POST /download

**Body (JSON):**

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "format": "best",
  "options": {}
}
```

- **url** – חובה. קישור לסרטון.
- **format** – אופציונלי (ברירת מחדל: `best`). דוגמאות: `best`, `mp4`, `mp3`, `bestvideo+bestaudio`, `137+140`.
- **options** – אופציונלי. מילון פרמטרים נוספים של yt-dlp (למשל `quality`, `postprocessor_args` וכו'). שדות כמו `outtmpl`/`paths` מתעלמים מהם מטעמי אבטחה.

**תגובה:** הקובץ ישירות (גוף התגובה = הקובץ, עם `Content-Disposition` לשם הקובץ).

### POST /download-list

**Body (JSON):**

```json
{
  "urls": [
    "https://www.youtube.com/watch?v=ID1",
    "https://www.youtube.com/watch?v=ID2"
  ],
  "format": "best",
  "options": {}
}
```

מחזיר קובץ ZIP עם כל הקבצים (עד 20 סרטונים בבקשה).

### דוגמת קריאה עם מזהה

```bash
curl -X POST "https://your-app.railway.app/download" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","format":"mp4"}' \
  --output video.mp4
```

## רישיון

MIT
