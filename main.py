"""
YouTube Download API - FastAPI server for downloading videos via pytubefix.
Deploy on Railway. Access with API key; pass params in request; get file back.
"""
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from pytubefix import YouTube

app = FastAPI(
    title="YouTube Download API",
    description="API for downloading YouTube videos (pytubefix). Authenticate with API key; pass params in body; receive file.",
    version="2.0.0",
)


def _get_proxy_dict() -> Optional[dict[str, str]]:
    """Build requests-style proxy dict from PROXY_URL env (http:// or socks5://)."""
    url = os.environ.get("PROXY_URL", "").strip()
    if not url:
        return None
    return {"http": url, "https": url}


def api_key_dep(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> None:
    expected = os.environ.get("API_KEY")
    if not expected:
        return
    token = x_api_key
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    if not token or token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class DownloadRequest(BaseModel):
    url: HttpUrl
    format: Optional[str] = "best"  # best, mp4, mp3 (audio)
    options: Optional[dict[str, Any]] = None  # reserved
    cookies_b64: Optional[str] = None  # not used with pytubefix; kept for API compatibility


class DownloadListRequest(BaseModel):
    urls: list[HttpUrl]
    format: Optional[str] = "best"
    options: Optional[dict[str, Any]] = None
    cookies_b64: Optional[str] = None


def _sanitize_filename(name: str) -> str:
    """Remove chars that are invalid in filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "video"


def _user_facing_error(msg: str) -> str:
    s = msg.strip()
    if "not available" in s.lower() or "private" in s.lower() or "unavailable" in s.lower():
        return (
            "YouTube reports this video as not available (e.g. age/region restriction). "
            "Try using a different network or proxy (PROXY_URL)."
        )
    return s


def download_video(
    url: str,
    format_str: str,
    out_dir: Path,
) -> Path:
    """Download a single video with pytubefix. Returns path to the downloaded file."""
    proxies = _get_proxy_dict()
    yt = YouTube(url, proxies=proxies)
    yt.check_availability()

    fmt = (format_str or "best").lower()
    stream = None

    if fmt == "mp3" or fmt == "audio":
        streams = yt.streams.filter(only_audio=True).order_by("abr").desc()
        stream = streams.first()
    elif fmt == "mp4":
        streams = yt.streams.filter(file_extension="mp4", progressive=True).order_by("resolution").desc()
        stream = streams.first()
        if not stream:
            streams = yt.streams.filter(file_extension="mp4").order_by("resolution").desc()
            stream = streams.first()
    else:
        # best: highest resolution (progressive when possible)
        stream = yt.streams.get_highest_resolution()

    if not stream:
        raise ValueError("No stream found for the requested format")

    safe_title = _sanitize_filename(yt.title)
    vid = getattr(yt, "video_id", "") or ""
    filename = f"{safe_title}_{vid}.{stream.subtype}" if vid else f"{safe_title}.{stream.subtype}"
    path = stream.download(output_path=str(out_dir), filename=filename, skip_existing=False)
    if path is None:
        raise ValueError("Download returned no path")
    return Path(path)


@app.get("/")
async def root():
    return {
        "service": "YouTube Download API (pytubefix)",
        "docs": "/docs",
        "auth": "When API_KEY env is set: send X-API-Key or Authorization: Bearer <key>. Optional PROXY_URL env = default proxy.",
        "endpoints": {
            "download": "POST /download - body: { url, format? } → file",
            "download-list": "POST /download-list - body: { urls, format? } → zip",
            "formats": "GET /formats?url=... - list formats",
        },
    }


@app.get("/formats")
async def list_formats(url: str, _: None = Depends(api_key_dep)):
    """List available streams for a video URL."""
    proxies = _get_proxy_dict()
    try:
        yt = YouTube(url, proxies=proxies)
        yt.check_availability()
    except Exception as e:
        raise HTTPException(status_code=400, detail=_user_facing_error(str(e)))
    streams = list(yt.streams)
    return {
        "title": yt.title,
        "formats": [
            {
                "itag": s.itag,
                "mime_type": s.mime_type,
                "resolution": s.resolution,
                "abr": getattr(s, "abr", None),
                "progressive": s.is_progressive,
                "type": "audio" if getattr(s, "includes_audio_track", False) else "video",
            }
            for s in streams[:60]
        ],
    }


def _cleanup_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


@app.post("/download")
async def download_single(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(api_key_dep),
):
    """Download a single video. Returns the file directly."""
    url = str(request.url)
    format_str = request.format or "best"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        try:
            path = download_video(url, format_str, out_dir)
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
    _: None = Depends(api_key_dep),
):
    """Download multiple videos. Returns a ZIP file."""
    if not request.urls or len(request.urls) > 20:
        raise HTTPException(status_code=400, detail="Provide 1-20 URLs")
    format_str = request.format or "best"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        downloaded: list[Path] = []
        errors: list[str] = []
        for i, url in enumerate(request.urls):
            try:
                path = download_video(str(url), format_str, out_dir)
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
