# פריסת הפרויקט ב-PythonAnywhere (שלב אחרי שלב)

FastAPI ב-PythonAnywhere רץ כ-**ASGI** דרך כלי שורת הפקודה `pa`, לא דרך דף ה-Web הרגיל. האתר שיופיע אצלך יהיה זה שתגדיר עם הפקודות למטה.

---

## שלב 1: להעלות את הקוד לשרת

1. ב-**Dashboard** של PythonAnywhere לחץ על **Consoles** → **Bash** (לפתוח טרמינל).
2. אם הקוד אצלך ב-Git:
   ```bash
   cd ~
   git clone https://github.com/YOUR_USERNAME/yt-dlp_api.git
   cd yt-dlp_api
   ```
   אם אין Git – צור תיקייה והעלה קבצים ידנית (למשל דרך **Files**):
   ```bash
   mkdir -p ~/yt-dlp_api
   cd ~/yt-dlp_api
   ```
   ואז העלה לשם את: `main.py`, `requirements.txt` (ו־`runtime.txt` אם יש).

שים לב: **YOUR_USERNAME** = שם המשתמש שלך ב-PythonAnywhere (למשל `yossibiton`). כל הנתיבים בהמשך משתמשים בו.

---

## שלב 2: יצירת סביבה וירטואלית (virtualenv) והתקנת חבילות

באותו **Bash console**:

```bash
# יצירת virtualenv (Python 3.10)
mkvirtualenv ytdlp_api --python=python3.10
```

אם אתה כבר בתוך virtualenv אחר, קודם: `deactivate`, ואז שוב:

```bash
workon ytdlp_api
cd ~/yt-dlp_api
pip install -r requirements.txt
```

וודא שההתקנה עברה בלי שגיאות (fastapi, uvicorn, yt-dlp, spotdl).

---

## שלב 3: התקנת כלי PythonAnywhere (לפריסת ASGI)

באותו Bash:

```bash
pip install --upgrade pythonanywhere
```

זה מתקין את הפקודה `pa`. אם מופיעה אזהרה על `typing-extensions` אפשר להתעלם.

---

## שלב 4: קבלת API Token (פעם אחת)

1. ב-Dashboard לחץ על **Account** (או **Account** בתפריט העליון).
2. גלול ל-**API Token**.
3. צור Token אם עדיין אין, והעתק אותו.  
   הפקודה `pa` בתוך Bash ב-PythonAnywhere משתמשת ב-Token הזה אוטומטית, אין צורך להדביק אותו בפקודות.

---

## שלב 5: יצירת אתר ה-ASGI (FastAPI)

בבאש (עם ה-virtualenv פעיל – `workon ytdlp_api`):

```bash
pa website create --domain YOURUSERNAME.pythonanywhere.com --command '/home/YOURUSERNAME/.virtualenvs/ytdlp_api/bin/uvicorn --app-dir /home/YOURUSERNAME/yt-dlp_api --uds ${DOMAIN_SOCKET} main:app'
```

**חשוב:** החלף **YOURUSERNAME** בשם המשתמש האמיתי שלך (פעמיים בפקודה).  
אם אתה על שרת **EU**, החלף את הדומיין ל: `YOURUSERNAME.eu.pythonanywhere.com`.

אם הכל עבד תראה הודעה שהאתר עלה.  
אפשר לפתוח בדפדפן: `https://YOURUSERNAME.pythonanywhere.com/` (או `.eu.pythonanywhere.com`).

---

## שלב 6: משתני סביבה (API_KEY, Spotify, פרוקסי)

- ב-PythonAnywhere (גרסת ASGI עם `pa`) אין עדיין מסך "Environment variables" לאתר.
- אפשרות פשוטה: להוסיף בפרויקט קובץ `.env` (רק אם אתה מוסיף `python-dotenv` ל-requirements ומטעין ב-`main.py`).
- אפשרות נוחה יותר: להגדיר משתנים ב-**Bash profile** כך שיהיו זמינים גם כש-`pa` מריץ את uvicorn (אם PythonAnywhere מעביר אותם לתהליך האתר).

בדוק בדף ה-**Web** אם יש שדה "Environment variables" או "Code" – אם כן, הזן שם למשל:

- `API_KEY=your_secret_key`
- `SPOTIFY_CLIENT_ID=...`
- `SPOTIFY_CLIENT_SECRET=...`
- `PROXY_URL=...` (אם צריך)

אם אין – ניתן להוסיף בפרויקט תמיכה ב-`.env` (קובץ שלא יעלה ל-Git) ולמלא שם את הערכים.

---

## שלב 7: FFmpeg (לפורמט MP3 ו-Spotify)

- **yt-dlp** עם פורמט `mp3` ו-**spotdl** צריכים FFmpeg על השרת.
- ב-Free tier של PythonAnywhere ייתכן ש-FFmpeg לא מותקן או לא זמין. אם תקבל שגיאות הקשורות ל-ffmpeg, תצטרך לשדרג או להריץ רק פורמטים שלא דורשים המרה (למשל `best` / `mp4` בלי `mp3`).

---

## שלב 8: עדכון קוד וריענון האתר

אחרי שינוי קוד או requirements:

```bash
cd ~/yt-dlp_api
pip install -r requirements.txt   # אם עדכנת תלויות
pa website reload --domain YOURUSERNAME.pythonanywhere.com
```

שוב – החלף `YOURUSERNAME` (ו־`.eu.` אם אתה על EU).

---

## סיכום פקודות שימושיות

| פעולה | פקודה |
|--------|--------|
| רשימת אתרים | `pa website get` |
| פרטי אתר | `pa website get --domain YOURUSERNAME.pythonanywhere.com` |
| ריענון אחרי שינוי קוד | `pa website reload --domain YOURUSERNAME.pythonanywhere.com` |
| מחיקת אתר | `pa website delete --domain YOURUSERNAME.pythonanywhere.com` |

לוגים (אם משהו נכשל):

- Error log: `/var/log/YOURUSERNAME.pythonanywhere.com.error.log`
- Server log: `/var/log/YOURUSERNAME.pythonanywhere.com.server.log`

ניתן לצפות בהם מהדף **Files** (נווט ל-`/var/log/`) או מהקונסולה.

---

## אם פתחת "Web app" בדף Web

- אם בחרת **Manual configuration** (או כל framework) ועכשיו יוצרת את האתר האמיתי עם `pa` – האתר שרץ הוא זה שהוגדר ב-`pa website create`.
- האפליקציה בדף ה-Web יכולה להישאר (ואז יהיו לך שני “אתרים” – אחד WSGI ואחד ASGI), או שאפשר למחוק את ה-Web app אם לא צריך אותה.
