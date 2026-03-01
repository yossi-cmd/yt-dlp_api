"""
YouTube Download API - FastAPI server for downloading videos via yt-dlp.
Deploy on Railway. Access with API key; pass all parameters in the request; get file back.
"""
import base64
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

import yt_dlp
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

app = FastAPI(
    title="YouTube Download API",
    description="API for downloading YouTube videos. Authenticate with API key; pass params in body; receive file.",
    version="1.0.0",
)

# Keys we never accept from the client (we control paths and safety)
FORBIDDEN_OPTIONS = frozenset({
    "outtmpl", "paths", "output", "output_na_placeholder",
    "postprocessor_args", "external_downloader_args", "concurrent_fragment_downloads",
    "cookiefile", "cookiesfrombrowser",
})


def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> None:
    """Validate API key from X-API-Key header or Authorization: Bearer <key>."""
    expected = os.environ.get("API_KEY")
    if not expected:
        return  # no key configured = allow all (e.g. local dev)
    token = x_api_key
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    if not token or token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class DownloadRequest(BaseModel):
    url: HttpUrl
    format: Optional[str] = "best"  # best, mp4, mp3, 137+140, etc.
    options: Optional[dict[str, Any]] = None  # extra yt-dlp options (outtmpl/paths ignored)
    cookies_b64: Optional[str] = None  # base64 of Netscape cookies.txt (for age/region-restricted)


class DownloadListRequest(BaseModel):
    urls: list[HttpUrl]
    format: Optional[str] = "best"
    options: Optional[dict[str, Any]] = None
    cookies_b64: Optional[str] = None


def _apply_default_proxy(opts: dict) -> None:
    """If PROXY_URL is set and no proxy in opts, use it as default."""
    if "proxy" in opts:
        return
    url = os.environ.get("PROXY_URL", "").strip()
    if url:
        opts["proxy"] = url


def _merge_opts(base: dict, extra: Optional[dict], out_dir: Path) -> dict:
    """Merge client options into base opts; forbid path-related keys."""
    out = {**base}
    if not extra:
        return out
    for k, v in extra.items():
        if k in FORBIDDEN_OPTIONS:
            continue
        out[k] = v
    out["outtmpl"] = str(out_dir / "%(title)s.%(ext)s")
    return out


def _user_facing_error(msg: str) -> str:
    """Turn yt-dlp errors into clearer messages; suggest cookies for 'not available'."""
    s = msg.strip()
    if "not available" in s.lower() or "private" in s.lower() or "unavailable" in s.lower():
        return (
            "YouTube reports this video as not available from the server (often age/region restriction). "
            "Use cookies from the browser where the video plays: install 'Get cookies.txt' (Chrome), "
            "export cookies for youtube.com, base64-encode the file and send it in the request as cookies_b64."
        )
    return s


def download_video(
    url: str,
    format_str: str,
    out_dir: Path,
    extra_opts: Optional[dict[str, Any]] = None,
    cookie_path: Optional[Path] = None,
) -> Path:
    """Download a single video with yt-dlp. Returns path to the downloaded file."""
    base = {
        "format": format_str,
        "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    if format_str.lower() in ("mp3", "m4a", "opus", "ogg", "wav"):
        base["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": format_str.lower()}
        ]
        base["format"] = "bestaudio/best"
    opts = _merge_opts(base, extra_opts, out_dir)
    if cookie_path is not None:
        opts["cookiefile"] = str(cookie_path)
    # Default proxy from env (e.g. PROXY_URL=http://user:pass@host:port)
    _apply_default_proxy(opts)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise ValueError("Could not extract video info")
        for f in out_dir.iterdir():
            if f.is_file():
                return f
    raise ValueError("Download completed but no file found")


@app.get("/")
async def root():
    return {
        "service": "YouTube Download API",
        "docs": "/docs",
        "auth": "When API_KEY env is set: send X-API-Key or Authorization: Bearer <key>. Optional PROXY_URL env = default proxy for all requests.",
        "endpoints": {
            "download": "POST /download - body: { url, format?, options? } → file",
            "download-list": "POST /download-list - body: { urls, format?, options? } → zip",
            "formats": "GET /formats?url=... - list formats for a video",
        },
    }


@app.get("/formats")
async def list_formats(url: str, _: None = Depends(require_api_key)):
    """List available formats for a video URL."""
    opts = {"quiet": True, "no_warnings": True}
    _apply_default_proxy(opts)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=400, detail="Invalid or unsupported URL")
            formats = info.get("formats") or []
            return {
                "title": info.get("title"),
                "formats": [
                    {
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "resolution": f.get("resolution") or f.get("height"),
                        "note": f.get("format_note"),
                    }
                    for f in formats
                    if f.get("vcodec") != "none" or f.get("acodec") != "none"
                ][:50],  # limit response size
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _cleanup_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def _cookie_file_from_b64(cookies_b64: Optional[str], tmpdir: Path) -> Optional[Path]:
    """Decode cookies_b64 and write to a temp file; return path or None."""
    if not cookies_b64:
        return None
    try:
        raw = base64.b64decode(cookies_b64, validate=True).decode("utf-8", errors="replace")
    except Exception:
        return None
    path = tmpdir / "cookies.txt"
    path.write_text(raw)
    return path


@app.post("/download")
async def download_single(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    """
    Download a single video. Pass url, format, optional `options`, optional `cookies_b64`.
    Returns the file directly.
    """
    url = str(request.url)
    format_str = request.format or "best"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        cookie_path = _cookie_file_from_b64(request.cookies_b64, out_dir)
        try:
            path = download_video(url, format_str, out_dir, request.options, cookie_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=_user_facing_error(str(e)))
        persistent = tempfile.NamedTemporaryFile(delete=False, suffix=path.suffix)
        persistent.write(path.read_bytes())
        persistent.close()
        background_tasks.add_task(_cleanup_file, persistent.name)
        return FileResponse(
            persistent.name,
            filename=path.name,
            media_type="application/octet-stream",
        )


@app.post("/download-list")
async def download_list(
    request: DownloadListRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    """
    Download multiple videos. Pass urls, format, optional `options`. Returns a ZIP.
    """
    if not request.urls or len(request.urls) > 20:
        raise HTTPException(
            status_code=400,
            detail="Provide 1-20 URLs",
        )
    format_str = request.format or "best"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        cookie_path = _cookie_file_from_b64(request.cookies_b64, out_dir)
        downloaded: list[Path] = []
        errors: list[str] = []
        for i, url in enumerate(request.urls):
            try:
                path = download_video(str(url), format_str, out_dir, request.options, cookie_path)
                downloaded.append(path)
            except Exception as e:
                errors.append(f"URL {i + 1}: {_user_facing_error(str(e))}")
        if not downloaded:
            raise HTTPException(
                status_code=400,
                detail="No videos could be downloaded. " + "; ".join(errors),
            )
        zip_path = out_dir / "downloads.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in downloaded:
                zf.write(p, p.name)
        persistent = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        persistent.write(zip_path.read_bytes())
        persistent.close()
        background_tasks.add_task(_cleanup_file, persistent.name)
        return FileResponse(
            persistent.name,
            filename="downloads.zip",
            media_type="application/zip",
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
