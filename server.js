/**
 * YouTube + Spotify Download API - Node.js (Express, ytdl-core, spottydl-better)
 * Deploy on Railway. API key auth, PROXY_URL support, returns file or zip.
 */
process.env.YTDL_NO_UPDATE = "1";
const express = require("express");
const fs = require("fs");
const path = require("path");
const os = require("os");
const archiver = require("archiver");

let SpottyDL;
function getSpottyDL() {
  if (!SpottyDL) SpottyDL = require("spottydl-better");
  return SpottyDL;
}

let ytdl;
function getYtdl() {
  if (!ytdl) {
    ytdl = require("@distube/ytdl-core");
  }
  return ytdl;
}

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 8000;
const API_KEY = process.env.API_KEY || "";
const PROXY_URL = (process.env.PROXY_URL || "").trim();

/** Parse cookies from body: cookies (array of {name, value}) or cookies_b64 (base64 Netscape format). */
function parseCookies(body) {
  if (!body) return null;
  if (Array.isArray(body.cookies) && body.cookies.length > 0) {
    const ok = body.cookies.every((c) => c && typeof c.name === "string" && typeof c.value === "string");
    if (ok) return body.cookies;
  }
  if (typeof body.cookies_b64 === "string" && body.cookies_b64.trim()) {
    try {
      const text = Buffer.from(body.cookies_b64.trim(), "base64").toString("utf8");
      const out = [];
      for (const line of text.split("\n")) {
        const t = line.trim();
        if (!t || t.startsWith("#")) continue;
        const parts = t.split("\t");
        if (parts.length >= 7) out.push({ name: parts[5], value: parts[6] });
      }
      if (out.length) return out;
    } catch (_) {}
  }
  return null;
}

function getAgent(cookiesFromRequest = null) {
  const lib = getYtdl();
  const hasProxy = !!PROXY_URL;
  const hasCookies = Array.isArray(cookiesFromRequest) && cookiesFromRequest.length > 0;
  try {
    if (hasProxy && hasCookies) return lib.createProxyAgent({ uri: PROXY_URL }, cookiesFromRequest);
    if (hasProxy) return lib.createProxyAgent({ uri: PROXY_URL });
    if (hasCookies) return lib.createAgent(cookiesFromRequest);
  } catch (_) {}
  return undefined;
}

function requireApiKey(req, res, next) {
  if (!API_KEY) return next();
  const token =
    req.headers["x-api-key"] ||
    (req.headers.authorization?.startsWith("Bearer ")
      ? req.headers.authorization.slice(7).trim()
      : null);
  if (!token || token !== API_KEY) {
    return res.status(401).json({ detail: "Invalid or missing API key" });
  }
  next();
}

function userFacingError(msg) {
  const s = String(msg).trim();
  if (/not available|private|unavailable/i.test(s)) {
    return "YouTube reports this video as not available (e.g. age/region restriction). Set PROXY_URL (residential proxy) and redeploy.";
  }
  if (/403|forbidden|status code: 403/i.test(s)) {
    return "YouTube returned 403 Forbidden (often blocks datacenter IPs). Set PROXY_URL in Railway Variables to a residential proxy (e.g. Bright Data, SmartProxy) and redeploy.";
  }
  return s;
}

function sanitizeFilename(name) {
  return (name || "video").replace(/[<>:"/\\|?*]/g, "_").trim() || "video";
}

app.get("/", (req, res) => {
  res.json({
    service: "YouTube + Spotify Download API (Node.js)",
    auth:
      API_KEY
        ? "Send X-API-Key or Authorization: Bearer <key>. Optional PROXY_URL = default proxy."
        : "No API_KEY set.",
    endpoints: {
      download: "POST /download - body: { url, format?, cookies? | cookies_b64? } → file (YouTube)",
      "download-list": "POST /download-list - body: { urls, format? } → zip (YouTube)",
      formats: "GET /formats?url=... - list formats (YouTube)",
      "spotify/track": "GET /spotify/track?url=... - track metadata (Spotify)",
      "spotify/download": "POST /spotify/download - body: { url } → MP3 (Spotify track)",
      "spotify/playlist": "POST /spotify/playlist - body: { url } → zip (Spotify playlist)",
      health: "GET /health - readiness check",
    },
  });
});

app.get("/health", (req, res) => {
  res.status(200).send("ok");
});

app.get("/formats", requireApiKey, async (req, res) => {
  const url = req.query.url;
  if (!url) {
    return res.status(400).json({ detail: "Missing url query" });
  }
  let lib;
  try {
    lib = getYtdl();
  } catch (e) {
    console.error("ytdl load error:", e);
    return res.status(503).json({ detail: "YouTube library not available. Check server logs." });
  }
  const agent = getAgent(parseCookies(req.body));
  try {
    const info = await lib.getInfo(url, agent ? { agent } : {});
    const formats = (info.formats || []).slice(0, 60).map((f) => ({
      itag: f.itag,
      mimeType: f.mimeType,
      quality: f.quality,
      qualityLabel: f.qualityLabel,
      audioBitrate: f.audioBitrate,
      container: f.container,
      hasVideo: f.hasVideo,
      hasAudio: f.hasAudio,
    }));
    res.json({ title: info.videoDetails?.title, formats });
  } catch (e) {
    res.status(400).json({ detail: userFacingError(e.message) });
  }
});

function chooseFormatOptions(formatStr) {
  const fmt = (formatStr || "best").toLowerCase();
  if (fmt === "mp3" || fmt === "audio") {
    return { quality: "highestaudio", filter: "audioonly" };
  }
  if (fmt === "mp4") {
    return { quality: "highest", filter: (f) => f.container === "mp4" && f.hasVideo };
  }
  return { quality: "highest", filter: "audioandvideo" };
}

async function downloadVideo(url, formatStr, outDir, cookiesFromRequest = null) {
  const lib = getYtdl();
  const agent = getAgent(cookiesFromRequest);
  const opts = agent ? { agent } : {};
  const info = await lib.getInfo(url, opts);
  const chooseOpts = chooseFormatOptions(formatStr);
  let format;
  try {
    format = lib.chooseFormat(info.formats, chooseOpts);
  } catch (e) {
    throw new Error("No stream found for the requested format");
  }
  const title = info.videoDetails?.title || "video";
  const videoId = info.videoDetails?.videoId || "";
  const ext = format.container || "mp4";
  const safeTitle = sanitizeFilename(title);
  const filename = videoId
    ? `${safeTitle}_${videoId}.${ext}`
    : `${safeTitle}.${ext}`;
  const filepath = path.join(outDir, filename);
  const stream = lib.downloadFromInfo(info, { ...opts, format });
  const write = fs.createWriteStream(filepath);
  await new Promise((resolve, reject) => {
    stream.pipe(write);
    write.on("finish", resolve);
    stream.on("error", reject);
    write.on("error", reject);
  });
  return filepath;
}

app.post("/download", requireApiKey, async (req, res) => {
  let lib;
  try {
    lib = getYtdl();
  } catch (e) {
    console.error("ytdl load error:", e);
    return res.status(503).json({ detail: "YouTube library not available. Check server logs." });
  }
  const { url, format: formatStr = "best" } = req.body || {};
  if (!url) {
    return res.status(400).json({ detail: "Missing url in body" });
  }
  const cookies = parseCookies(req.body);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "yt-"));
  let filepath;
  try {
    filepath = await downloadVideo(url, formatStr, tmpDir, cookies);
  } catch (e) {
    try {
      fs.rmSync(tmpDir, { recursive: true });
    } catch {}
    return res.status(400).json({ detail: userFacingError(e.message) });
  }
  const filename = path.basename(filepath);
  res.download(filepath, filename, (err) => {
    try {
      fs.unlinkSync(filepath);
      fs.rmSync(tmpDir, { recursive: true });
    } catch {}
  });
});

app.post("/download-list", requireApiKey, async (req, res) => {
  try {
    getYtdl();
  } catch (e) {
    console.error("ytdl load error:", e);
    return res.status(503).json({ detail: "YouTube library not available. Check server logs." });
  }
  const { urls, format: formatStr = "best" } = req.body || {};
  if (!Array.isArray(urls) || urls.length === 0 || urls.length > 20) {
    return res.status(400).json({ detail: "Provide 1-20 URLs" });
  }
  const cookies = parseCookies(req.body);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "yt-"));
  const downloaded = [];
  const errors = [];
  for (let i = 0; i < urls.length; i++) {
    try {
      const filepath = await downloadVideo(urls[i], formatStr, tmpDir, cookies);
      downloaded.push(filepath);
    } catch (e) {
      errors.push(`URL ${i + 1}: ${userFacingError(e.message)}`);
    }
  }
  if (downloaded.length === 0) {
    try {
      fs.rmSync(tmpDir, { recursive: true });
    } catch {}
    return res.status(400).json({
      detail: "No videos could be downloaded. " + errors.join("; "),
    });
  }
  const zipPath = path.join(tmpDir, "downloads.zip");
  const output = fs.createWriteStream(zipPath);
  const archive = archiver("zip", { zlib: { level: 9 } });
  archive.pipe(output);
  for (const fp of downloaded) {
    archive.file(fp, { name: path.basename(fp) });
  }
  await archive.finalize();
  await new Promise((resolve, reject) => {
    output.on("close", resolve);
    archive.on("error", reject);
  });
  res.download(zipPath, "downloads.zip", (err) => {
    try {
      for (const fp of downloaded) fs.unlinkSync(fp);
      fs.unlinkSync(zipPath);
      fs.rmSync(tmpDir, { recursive: true });
    } catch {}
  });
});

// ---------- Spotify (spottydl-better: resolves via YouTube Music, needs FFmpeg) ----------

function isSpotifyUrl(url) {
  return /^https?:\/\/(open\.)?spotify\.com\/(track|album|playlist)\//i.test(String(url || "").trim());
}

app.get("/spotify/track", requireApiKey, async (req, res) => {
  const url = req.query.url;
  if (!url || !isSpotifyUrl(url)) {
    return res.status(400).json({ detail: "Missing or invalid Spotify track/album/playlist URL" });
  }
  try {
    const lib = getSpottyDL();
    const trackUrl = url.replace(/\/album\/.*/, "").replace(/\/playlist\/.*/, "").trim();
    if (!/\/track\//i.test(trackUrl)) {
      return res.status(400).json({ detail: "Use a Spotify track URL for /spotify/track" });
    }
    const track = await lib.getTrack(trackUrl);
    return res.json(track);
  } catch (e) {
    return res.status(400).json({ detail: String(e.message || e).trim() });
  }
});

app.post("/spotify/download", requireApiKey, async (req, res) => {
  const { url } = req.body || {};
  if (!url || !isSpotifyUrl(url) || !/\/track\//i.test(url)) {
    return res.status(400).json({ detail: "Missing or invalid Spotify track URL" });
  }
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "spot-"));
  try {
    const lib = getSpottyDL();
    const track = await lib.getTrack(url);
    const results = await lib.downloadTrack(track, tmpDir);
    const success = results && results[0] && results[0].status === "Success" && results[0].filename;
    if (!success || !fs.existsSync(results[0].filename)) {
      try {
        fs.rmSync(tmpDir, { recursive: true });
      } catch {}
      return res.status(400).json({
        detail: (results && results[0] && results[0].status) || "Download failed",
      });
    }
    const filepath = results[0].filename;
    const filename = path.basename(filepath);
    res.download(filepath, filename, (err) => {
      try {
        fs.unlinkSync(filepath);
        fs.rmSync(tmpDir, { recursive: true });
      } catch {}
    });
  } catch (e) {
    try {
      fs.rmSync(tmpDir, { recursive: true });
    } catch {}
    return res.status(400).json({ detail: String(e.message || e).trim() });
  }
});

app.post("/spotify/playlist", requireApiKey, async (req, res) => {
  const { url } = req.body || {};
  if (!url || !isSpotifyUrl(url)) {
    return res.status(400).json({ detail: "Missing or invalid Spotify playlist/album URL" });
  }
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "spot-"));
  try {
    const lib = getSpottyDL();
    const isPlaylist = /\/playlist\//i.test(url);
    const list = isPlaylist ? await lib.getPlaylist(url) : await lib.getAlbum(url);
    const downloadMethod = isPlaylist ? lib.downloadPlaylist.bind(lib) : lib.downloadAlbum.bind(lib);
    const results = await downloadMethod(list, tmpDir, false);
    const files = (results || []).filter((r) => r.status === "Success" && r.filename && fs.existsSync(r.filename)).map((r) => r.filename);
    if (files.length === 0) {
      try {
        fs.rmSync(tmpDir, { recursive: true });
      } catch {}
      return res.status(400).json({
        detail: "No tracks could be downloaded. " + ((results && results[0] && results[0].status) || "Check URL and try again."),
      });
    }
    const zipPath = path.join(tmpDir, "spotify.zip");
    const output = fs.createWriteStream(zipPath);
    const archive = archiver("zip", { zlib: { level: 9 } });
    archive.pipe(output);
    for (const fp of files) archive.file(fp, { name: path.basename(fp) });
    await archive.finalize();
    await new Promise((resolve, reject) => {
      output.on("close", resolve);
      archive.on("error", reject);
    });
    res.download(zipPath, "spotify.zip", (err) => {
      try {
        for (const fp of files) fs.unlinkSync(fp);
        fs.unlinkSync(zipPath);
        fs.rmSync(tmpDir, { recursive: true });
      } catch {}
    });
  } catch (e) {
    try {
      fs.rmSync(tmpDir, { recursive: true });
    } catch {}
    return res.status(400).json({ detail: String(e.message || e).trim() });
  }
});

const server = app.listen(PORT, "0.0.0.0", () => {
  console.log(`YouTube + Spotify Download API listening on port ${PORT}`);
});
server.on("error", (err) => {
  console.error("Server listen error:", err);
  process.exit(1);
});
