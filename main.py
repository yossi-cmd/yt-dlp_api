"""
YouTube + Spotify Download API - Python (FastAPI, yt-dlp, spotdl).
Deploy on Railway. API key auth, PROXY_URL support, returns file or zip.
"""
import base64
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

# --- Config ---
API_KEY = (__import__("os").environ.get("API_KEY") or "").strip()
PROXY_URL = (__import__("os").environ.get("PROXY_URL") or "").strip()
SPOTIFY_CLIENT_ID = (__import__("os").environ.get("SPOTIFY_CLIENT_ID") or "").strip()
SPOTIFY_CLIENT_SECRET = (__import__("os").environ.get("SPOTIFY_CLIENT_SECRET") or "").strip()

app = FastAPI(title="YouTube + Spotify Download API")


def require_api_key(request: Request):
    if not API_KEY:
        return
    token = request.headers.get("x-api-key") or (
        request.headers.get("authorization") or ""
    ).replace("Bearer ", "").strip()
    if not token or token != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def parse_cookies(body: dict | None) -> str | None:
    """Return path to a temp Netscape cookie file, or None."""
    if not body:
        return None
    lines = []
    if isinstance(body.get("cookies"), list):
        for c in body["cookies"]:
            if isinstance(c, dict) and isinstance(c.get("name"), str) and isinstance(c.get("value"), str):
                # Netscape: domain, flag, path, secure, expiry, name, value
                lines.append(f".youtube.com\tTRUE\t/\tFALSE\t0\t{c['name']}\t{c['value']}")
    elif isinstance(body.get("cookies_b64"), str) and body["cookies_b64"].strip():
        try:
            raw = base64.b64decode(body["cookies_b64"].strip()).decode("utf-8")
            lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        except Exception:
            return None
    if not lines:
        return None
    header = "# Netscape HTTP Cookie File\n"
    fd, path = tempfile.mkstemp(suffix=".txt")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines))
    return path


def user_facing_error(msg: str) -> str:
    s = (msg or "").strip()
    if re.search(r"not available|private|unavailable", s, re.I):
        return "YouTube reports this video as not available (e.g. age/region restriction). Set PROXY_URL (residential proxy) and redeploy."
    if re.search(r"403|forbidden|status code: 403", s, re.I):
        return "YouTube returned 403 Forbidden (often blocks datacenter IPs). Set PROXY_URL in Railway Variables to a residential proxy and redeploy."
    return s


def sanitize_filename(name: str) -> str:
    return (name or "video").replace('"', "'").replace("\\", "_").replace("/", "_").strip() or "video"


# ---------- YouTube (yt-dlp) ----------
def get_ytdl_opts(cookie_file: str | None, format_str: str) -> dict:
    opts = {}
    if PROXY_URL:
        opts["proxy"] = PROXY_URL
    if cookie_file:
        opts["cookiefile"] = cookie_file
    fmt = (format_str or "best").lower()
    if fmt in ("mp3", "audio"):
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
    elif fmt == "mp4":
        opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    else:
        opts["format"] = "best"
    return opts


@app.get("/")
async def root():
    return {
        "service": "YouTube + Spotify Download API (Python)",
        "auth": "Send X-API-Key or Authorization: Bearer <key>. Optional PROXY_URL = default proxy." if API_KEY else "No API_KEY set.",
        "endpoints": {
            "download": "POST /download - body: { url, format?, cookies? | cookies_b64? } → file (YouTube)",
            "download-list": "POST /download-list - body: { urls, format? } → zip (YouTube)",
            "formats": "GET /formats?url=... - list formats (YouTube)",
            "spotify/track": "GET /spotify/track?url=... - track metadata (Spotify)",
            "spotify/download": "POST /spotify/download - body: { url } → MP3 (Spotify track)",
            "spotify/playlist": "POST /spotify/playlist - body: { url } → zip (Spotify playlist)",
            "health": "GET /health - readiness check",
        },
    }


@app.get("/health")
async def health():
    return "ok"


@app.get("/formats")
async def formats(
    url: str = Query(..., description="YouTube video URL"),
    _: None = Depends(require_api_key),
):
    import yt_dlp
    try:
        opts = get_ytdl_opts(None, "best")
        opts["quiet"] = True
        opts["extract_flat"] = False
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise HTTPException(status_code=400, detail="Could not get video info")
        entries = info.get("entries") or [info]
        formatters = []
        for e in entries[:1]:
            for f in (e.get("formats") or [])[:60]:
                formatters.append({
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "resolution": f.get("resolution"),
                    "vcodec": f.get("vcodec"),
                    "acodec": f.get("acodec"),
                })
        return {"title": info.get("title"), "formats": formatters}
    except Exception as e:
        raise HTTPException(status_code=400, detail=user_facing_error(str(e)))


@app.post("/download")
async def download(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    import yt_dlp
    body = await request.json() or {}
    url = body.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing url in body")
    format_str = body.get("format", "best")
    cookie_file = parse_cookies(body)
    tmp_dir = tempfile.mkdtemp(prefix="yt-")
    out_path = None
    try:
        opts = get_ytdl_opts(cookie_file, format_str)
        opts["outtmpl"] = str(Path(tmp_dir) / "%(title)s_%(id)s.%(ext)s")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        if not info:
            raise HTTPException(status_code=400, detail="Could not download video")
        title = info.get("title") or "video"
        video_id = info.get("id") or ""
        ext = info.get("ext") or "mp4"
        if format_str and format_str.lower() in ("mp3", "audio"):
            ext = "mp3"
        candidates = list(Path(tmp_dir).glob("*"))
        for p in candidates:
            if p.is_file():
                out_path = p
                break
        if not out_path or not out_path.is_file():
            raise HTTPException(status_code=400, detail="Download produced no file")
        filename = f"{sanitize_filename(title)}_{video_id}.{ext}" if video_id else f"{sanitize_filename(title)}.{ext}"
        response = FileResponse(path=str(out_path), filename=filename, media_type="application/octet-stream")
        def cleanup():
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            if cookie_file and Path(cookie_file).exists():
                try:
                    Path(cookie_file).unlink(missing_ok=True)
                except Exception:
                    pass
        background_tasks.add_task(cleanup)
        return response
    except HTTPException:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if cookie_file and Path(cookie_file).exists():
            try:
                Path(cookie_file).unlink(missing_ok=True)
            except Exception:
                pass
        raise
    except Exception as e:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if cookie_file and Path(cookie_file).exists():
            try:
                Path(cookie_file).unlink(missing_ok=True)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=user_facing_error(str(e)))


@app.post("/download-list")
async def download_list(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    import yt_dlp
    body = await request.json() or {}
    urls = body.get("urls")
    if not isinstance(urls, list) or len(urls) == 0 or len(urls) > 20:
        raise HTTPException(status_code=400, detail="Provide 1-20 URLs")
    format_str = body.get("format", "best")
    cookie_file = parse_cookies(body)
    tmp_dir = tempfile.mkdtemp(prefix="yt-")
    downloaded = []
    errors = []
    opts = get_ytdl_opts(cookie_file, format_str)
    opts["outtmpl"] = str(Path(tmp_dir) / "%(title)s_%(id)s.%(ext)s")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            for i, url in enumerate(urls):
                try:
                    ydl.download([url])
                except Exception as e:
                    errors.append(f"URL {i + 1}: {user_facing_error(str(e))}")
        for p in Path(tmp_dir).iterdir():
            if p.is_file() and not p.suffix == ".zip":
                downloaded.append(p)
        if not downloaded:
            raise HTTPException(
                status_code=400,
                detail="No videos could be downloaded. " + ("; ".join(errors) if errors else "Unknown error"),
            )
        zip_path = Path(tmp_dir) / "downloads.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in downloaded:
                zf.write(p, p.name)
        response = FileResponse(path=str(zip_path), filename="downloads.zip", media_type="application/zip")
        def cleanup():
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            if cookie_file and Path(cookie_file).exists():
                try:
                    Path(cookie_file).unlink(missing_ok=True)
                except Exception:
                    pass
        background_tasks.add_task(cleanup)
        return response
    except HTTPException:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if cookie_file and Path(cookie_file).exists():
            try:
                Path(cookie_file).unlink(missing_ok=True)
            except Exception:
                pass
        raise
    except Exception as e:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if cookie_file and Path(cookie_file).exists():
            try:
                Path(cookie_file).unlink(missing_ok=True)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=user_facing_error(str(e)))


# ---------- Spotify (spotdl) ----------
def is_spotify_url(url: str) -> bool:
    return bool(re.match(r"^https?://(open\.)?spotify\.com/(track|album|playlist)/", (url or "").strip(), re.I))


def get_spotdl(output_dir: str):
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Spotify not configured. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.",
        )
    from spotdl import Spotdl
    return Spotdl(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        downloader_settings={
            "output": output_dir,
            "scan_for_songs": False,
        },
    )


@app.get("/spotify/track")
async def spotify_track(
    url: str = Query(..., description="Spotify track URL"),
    _: None = Depends(require_api_key),
):
    if not url or not is_spotify_url(url):
        raise HTTPException(status_code=400, detail="Missing or invalid Spotify track/album/playlist URL")
    if "/track/" not in url.lower():
        raise HTTPException(status_code=400, detail="Use a Spotify track URL for /spotify/track")
    tmp = tempfile.mkdtemp(prefix="spot-")
    try:
        spotdl = get_spotdl(tmp)
        songs = spotdl.search([url])
        if not songs:
            raise HTTPException(status_code=400, detail="Track not found")
        song = songs[0]
        data = getattr(song, "json", None) or {
            "name": getattr(song, "name", None),
            "artist": getattr(song, "artist", None),
            "artists": getattr(song, "artists", None),
            "album": getattr(song, "album_name", None) or getattr(song, "album", None),
            "url": getattr(song, "url", None),
        }
        return JSONResponse(content=data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e).strip())
    finally:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


@app.post("/spotify/download")
async def spotify_download(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    body = await request.json() or {}
    url = (body.get("url") or "").strip()
    if not url or not is_spotify_url(url) or "/track/" not in url.lower():
        raise HTTPException(status_code=400, detail="Missing or invalid Spotify track URL")
    tmp_dir = tempfile.mkdtemp(prefix="spot-")
    try:
        spotdl = get_spotdl(tmp_dir)
        songs = spotdl.search([url])
        if not songs:
            raise HTTPException(status_code=400, detail="Track not found")
        _, path = spotdl.download(songs[0])
        if not path or not Path(path).exists():
            raise HTTPException(status_code=400, detail="Download failed")
        file_path = Path(path)
        response = FileResponse(path=str(file_path), filename=file_path.name, media_type="audio/mpeg")
        def cleanup():
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
        background_tasks.add_task(cleanup)
        return response
    except HTTPException:
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e).strip())


@app.post("/spotify/playlist")
async def spotify_playlist(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    body = await request.json() or {}
    url = (body.get("url") or "").strip()
    if not url or not is_spotify_url(url):
        raise HTTPException(status_code=400, detail="Missing or invalid Spotify playlist/album URL")
    tmp_dir = tempfile.mkdtemp(prefix="spot-")
    try:
        spotdl = get_spotdl(tmp_dir)
        songs = spotdl.search([url])
        if not songs:
            raise HTTPException(status_code=400, detail="Playlist/album not found or empty")
        results = spotdl.download_songs(songs)
        files = [Path(p) for _, p in results if p and Path(p).exists()]
        if not files:
            raise HTTPException(status_code=400, detail="No tracks could be downloaded.")
        zip_path = Path(tmp_dir) / "spotify.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.name)
        response = FileResponse(path=str(zip_path), filename="spotify.zip", media_type="application/zip")
        def cleanup():
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
        background_tasks.add_task(cleanup)
        return response
    except HTTPException:
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e).strip())
