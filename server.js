/**
 * YouTube Download API - Node.js (Express + @distube/ytdl-core)
 * Deploy on Railway. API key auth, PROXY_URL support, returns file or zip.
 */
process.env.YTDL_NO_UPDATE = "1";
const express = require("express");
const fs = require("fs");
const path = require("path");
const os = require("os");
const archiver = require("archiver");

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

function getAgent() {
  if (!PROXY_URL) return undefined;
  try {
    return getYtdl().createProxyAgent({ uri: PROXY_URL });
  } catch {
    return undefined;
  }
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
  if (
    /not available|private|unavailable/i.test(s)
  ) {
    return "YouTube reports this video as not available (e.g. age/region restriction). Try PROXY_URL or different network.";
  }
  return s;
}

function sanitizeFilename(name) {
  return (name || "video").replace(/[<>:"/\\|?*]/g, "_").trim() || "video";
}

app.get("/", (req, res) => {
  res.json({
    service: "YouTube Download API (Node.js)",
    auth:
      API_KEY
        ? "Send X-API-Key or Authorization: Bearer <key>. Optional PROXY_URL = default proxy."
        : "No API_KEY set.",
    endpoints: {
      download: "POST /download - body: { url, format? } → file",
      "download-list": "POST /download-list - body: { urls, format? } → zip",
      formats: "GET /formats?url=... - list formats",
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
  const agent = getAgent();
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

async function downloadVideo(url, formatStr, outDir) {
  const lib = getYtdl();
  const agent = getAgent();
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
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "yt-"));
  let filepath;
  try {
    filepath = await downloadVideo(url, formatStr, tmpDir);
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
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "yt-"));
  const downloaded = [];
  const errors = [];
  for (let i = 0; i < urls.length; i++) {
    try {
      const filepath = await downloadVideo(urls[i], formatStr, tmpDir);
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

const server = app.listen(PORT, "0.0.0.0", () => {
  console.log(`YouTube Download API listening on port ${PORT}`);
});
server.on("error", (err) => {
  console.error("Server listen error:", err);
  process.exit(1);
});
