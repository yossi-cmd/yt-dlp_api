"""
YouTube Download API - FastAPI server for downloading videos via yt-dlp.
Deploy on Railway. Access with API key; pass all parameters in the request; get file back.
"""
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


class DownloadListRequest(BaseModel):
    urls: list[HttpUrl]
    format: Optional[str] = "best"
    options: Optional[dict[str, Any]] = None


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


def download_video(
    url: str,
    format_str: str,
    out_dir: Path,
    extra_opts: Optional[dict[str, Any]] = None,
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
        "auth": "When API_KEY env is set: send X-API-Key or Authorization: Bearer <key> on /download, /download-list, /formats",
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


@app.post("/download")
async def download_single(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    """
    Download a single video. Pass url, format, and optional `options` (yt-dlp dict).
    Returns the file directly.
    """
    url = str(request.url)
    format_str = request.format or "best"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        try:
            path = download_video(url, format_str, out_dir, request.options)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
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
        downloaded: list[Path] = []
        errors: list[str] = []
        for i, url in enumerate(request.urls):
            try:
                path = download_video(str(url), format_str, out_dir, request.options)
                downloaded.append(path)
            except Exception as e:
                errors.append(f"URL {i + 1}: {e}")
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
