# YouTube Download API

תשתית API להורדת סרטונים מ-YouTube: גישה עם מזהה (API Key), העברת כל הפרמטרים בבקשה, וקבלת הקובץ ישירות בתגובה. מתאים לפריסה ב-Railway.

## אימות (API Key)

כשמוגדר משתנה סביבה `API_KEY` ב-Railway (או locally), יש לשלוח את המזהה בכל בקשה ל-`/download`, `/download-list` ו-`/formats`:

- **Header:** `X-API-Key: <your-api-key>`
- **או:** `Authorization: Bearer <your-api-key>`

אם `API_KEY` לא מוגדר, האימות מושבת (נוח לפיתוח מקומי).

### פרוקסי כברירת מחדל (PROXY_URL)

אם מוגדר משתנה סביבה `PROXY_URL` (למשל ב-Railway), השרת ישתמש בו אוטומטית בכל הבקשות ל-`/download`, `/download-list` ו-`/formats`, אלא אם הבקשה מעבירה `options.proxy` משלה.

דוגמה:
```bash
PROXY_URL=http://user:password@brd.superproxy.io:33335
```

כדי לבטל פרוקסי בבקשה בודדת, העבר `"options": {"proxy": ""}` או `"options": {"proxy": null}` (תלוי ב-yt-dlp).

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
- **options** – אופציונלי. מילון פרמטרים נוספים של yt-dlp (למשל `proxy` – ראו למטה).
- **cookies_b64** – אופציונלי. קובץ cookies בפורמט Netscape מקודד ב-base64. עוזר לסרטונים עם הגבלת גיל/אזור.

**תגובה:** הקובץ ישירות (גוף התגובה = הקובץ, עם `Content-Disposition` לשם הקובץ).

### למה מתקבל "This video is not available" (בלי cookies)?

**סיבה:** יוטיוב מזהה IP של **דאטהסנטר** (שרתי ענן כמו Railway, AWS, וכו') ומחזיר "video is not available" גם כשהסרטון קיים ונגיש ממחשב/נייד רגיל. זה מתועד ב-[yt-dlp](https://github.com/yt-dlp/yt-dlp/issues/16072) ו-[pytube](https://github.com/pytube/pytube/issues/1667): אין הבדל בצד הלקוח בין "סרטון לא קיים" ל"יוטיוב חוסם את ה-IP" – ההחלטה בצד השרת.

**פתרון בלי cookies – Proxy עם IP "רגיל" (residential):**  
אם התעבורה יוצאת דרך פרוקסי עם IP שלא מזוהה כדאטהסנטר, יוטיוב לרוב לא חוסם. אפשר להעביר ל-yt-dlp פרוקסי דרך השדה `options`:

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "format": "best",
  "options": {
    "proxy": "http://user:password@proxy-host:port"
  }
}
```

לפרוקסי SOCKS5:
```json
"options": { "proxy": "socks5://user:password@proxy-host:port" }
```

דוגמה עם Bright Data (ממיר מ־curl עם `--proxy` ו־`--proxy-user`):
- פרוקסי: `brd.superproxy.io:33335`, משתמש: `brd-customer-hl_XXX-zone-datacenter_proxy1`, סיסמה: `YYY`
- ב־API: `"options": { "proxy": "http://brd-customer-hl_XXX-zone-datacenter_proxy1:YYY@brd.superproxy.io:33335" }`
- אם יוטיוב עדיין מחזיר "not available", לעבור ל־**residential** ב־Bright Data (zone שלא כולל `datacenter`).

**ספקי פרוקסי מומלצים (residential):**
- **[Oxylabs](https://oxylabs.io/products/residential-proxies)** – כיסוי גלובלי, שיעור הצלחה גבוה, מתאים ל־enterprise.
- **[SmartProxy](https://smartproxy.com)** – מיליוני IPים, HTTP ו־SOCKS5, מחיר תחרותי.
- **[Bright Data](https://brightdata.com)** – רשת גדולה, אפשרות ל־residential ו־datacenter.
- **מחיר נמוך יותר:** [Tabproxy](https://www.tabproxy.com), [FlashProxy](https://flashproxy.com) – מתאימים לנפח קטן–בינוני.

**אפשרויות חינמיות (מוגבלות):**
- **ניסיון חינם:** לרוב הספקים above יש trial (למשל [Bright Data](https://brightdata.com) – שבוע חינם, [Oxylabs](https://oxylabs.io), [SmartProxy](https://smartproxy.com) – גישה לניסיון). מתאים לבדיקה.
- **Tor:** `options: { "proxy": "socks5://127.0.0.1:9050" }` – רק אם Tor רץ אצלך; יוטיוב לעיתים חוסם גם IP של Tor, אז לא תמיד יעבוד.
- **רשימות פרוקסי חינמיות (אינטרנט):** בדרך כלל datacenter/ציבורי – יוטיוב חוסם רובם, איטי ולא יציב. לא מומלץ ל־YouTube.

חשוב: לבחור **residential** (לא רק datacenter) כדי שיוטיוב לא יחסום. מכניסים את כתובת הפרוקסי (כולל user:password אם יש) ב-`options.proxy`.  
**הערה:** `geo-verification-proxy` של yt-dlp [לא עובד טוב על יוטיוב](https://github.com/yt-dlp/yt-dlp/issues/697); עדיף `proxy` רגיל.

### אם מתקבל "This video is not available" (עם cookies)

אם אתה מעדיף לא להשתמש בפרוקסי, אפשר לשלוח cookies מהדפדפן שבו הסרטון עובד.

1. **ייצוא cookies:** התקן [Get cookies.txt](https://chromewebstore.google.com/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid), היכנס ל-youtube.com (ואם צריך צפה בסרטון), לחץ על ההרחבה → Export → שמור כ־`cookies.txt`.
2. **קידוד ל-base64** (טרמינל):
   ```bash
   # macOS/Linux
   base64 -i cookies.txt | tr -d '\n' > cookies_b64.txt
   ```
3. **שליחה ב-API:** העתק את התוכן של `cookies_b64.txt` לשדה `cookies_b64` בבקשה (ב-JSON body).

דוגמה עם curl (מחליף את `PASTE_BASE64_HERE` בתוכן של cookies_b64.txt):
```bash
curl -X POST "https://YOUR-APP.railway.app/download" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=_stS2OuIM0M","format":"best","cookies_b64":"PASTE_BASE64_HERE"}' \
  --output video.mp4
```

### POST /download-list

**Body (JSON):**

```json
{
  "urls": [
    "https://www.youtube.com/watch?v=ID1",
    "https://www.youtube.com/watch?v=ID2"
  ],
  "format": "best",
  "options": {},
  "cookies_b64": null
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
