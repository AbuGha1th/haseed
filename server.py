"""Haseed — a small local web page for downloading videos with yt-dlp.

Start it with start.command (Mac) or start.bat (Windows).
"""
import json
import re
import secrets
import socket
import time
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
# Tools installed into the venv (deno) must be on PATH for yt-dlp to find them
os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
try:
    import static_ffmpeg
    static_ffmpeg.add_paths(weak=True)  # use a system ffmpeg if there is one, else a bundled copy
except ImportError:
    pass
import yt_dlp  # noqa: E402

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
DESKTOP = os.path.expanduser("~/Desktop")
OUT = os.environ.get("HASEED_OUT") or os.path.join(DESKTOP if os.path.isdir(DESKTOP) else os.path.expanduser("~"), "Haseed")
IS_ANDROID_APP = bool(os.environ.get("HASEED_ANDROID"))
PORT = int(os.environ.get("PORT", 8788))
HAS_FFMPEG = shutil.which("ffmpeg") is not None
JS = {"deno": {}, "node": {}}

def pick_format(kind):
    """kind is 'audio', 'best', or a max height like '2160'."""
    if kind == "audio":
        return "ba/b"
    if kind.isdigit():
        h = int(kind)
        return f"bv*[height<={h}]+ba/b[height<={h}]/wv*+ba/w"  # none that small: take the smallest there is
    return "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"  # unknown sizes: stay at 1080p or below


# Haseed refuses adult content, three ways:
# 1. these sites, named as yt-dlp names them (its own 18+ marking also catches general
#    sites like YouTube or Reddit, so this list is picked by hand from it),
ADULT_SITES = frozenset("""
    AlphaPorno Beeg BehindKink BongaCams CAM4 Camsoda Chaturbate DrTuber EMPFlix Eporner
    EroProfile Erocast FourTube Fux HellPorno Iwara LoveHomePorn MovieFap Murrtube MyVidster
    NonkTube NoodleMagazine NubilesPorn Nuvid PeekVids PlayVids PornFlip PornHub PornTop
    PornTube Pornbox PornerBros PornoVoisines PornoXO Pornotube Pr0gramm RedGifs RedTube
    Rule34Video Scrolller Sexu Slutload SpankBang Stripchat SunPorno TNAFlix TNAFlixNetworkEmbed
    ThisVid ThisVidPlaylist Toypics Tube8 Txxx XHamster XHamsterEmbed XNXX XVideos
    XVideosQuickies XXXYMovies YouJizz YouPorn ZenPorn
""".split())
# 2. any site whose address contains one of these words (for sites yt-dlp doesn't name),
ADULT_ADDRESS = re.compile(
    r"porn|xxx|nsfw|hentai|onlyfans|fansly|xvideo|xnxx|xhamster|redtube|youjizz|camgirl|rule34"
    r"|(?:^|[.-])(?:sex|nude|erotic|milf)")  # these only at the start of a name part: not "essex"
# 3. any single video a site marks 18+ (yt-dlp's age_limit), e.g. on YouTube or Reddit.
AGE_LIMIT = 17
BLOCKED = "Haseed doesn't download adult content"
_SITES = list(yt_dlp.extractor.gen_extractor_classes())


def check_allowed(url):
    host = (urlparse(url).hostname or "").lower()
    site = next((ie.ie_key() for ie in _SITES if ie.ie_key() != "Generic" and ie.suitable(url)), None)
    if site in ADULT_SITES or ADULT_ADDRESS.search(host):
        raise RuntimeError(BLOCKED)


def probe(url):
    check_allowed(url)
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True, "js_runtimes": JS,
                           "age_limit": AGE_LIMIT}) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get("extractor_key") in ADULT_SITES or (info.get("age_limit") or 0) > AGE_LIMIT:
        raise RuntimeError(BLOCKED)
    # Name each size by its width, so odd sizes (e.g. 3600x2026) still read as "4K"
    names = [(3200, "4K"), (2300, "1440p"), (1700, "1080p"), (1100, "720p"), (750, "480p"), (560, "360p")]
    qualities = {}
    for f in info.get("formats") or []:
        w, h = f.get("width"), f.get("height")
        if not (w and h):
            continue
        label = next((n for limit, n in names if max(w, h) >= limit), None)
        if label and h > qualities.get(label, 0):
            qualities[label] = h
    ranked = [(n, qualities[n]) for _, n in names if n in qualities]
    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "site": info.get("extractor_key"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "qualities": [{"label": n, "height": h} for n, h in ranked],
    }


JOBS = {}


def fetch(url, kind, job):
    check_allowed(url)
    tmp = tempfile.mkdtemp(prefix="haseed-")

    def on_progress(d):
        if d["status"] not in ("downloading", "finished"):
            return
        info = d.get("info_dict", {})
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        frac = 1 if d["status"] == "finished" else (d.get("downloaded_bytes", 0) / total if total else 0)
        frac = min(frac, 1)
        # YouTube etc. send video and audio as two files, one after the other.
        # Show one bar across both: video fills 0-90%, the (small) audio 90-100%.
        if kind != "audio" and info.get("acodec") == "none":
            label, percent = "Downloading video", 90 * frac
        elif kind != "audio" and info.get("vcodec") == "none":
            label, percent = "Downloading audio", 90 + 10 * frac
        else:
            label, percent = "Downloading", 100 * frac
        job.update(stage="downloading", label=label, percent=round(percent, 1),
                   speed=d.get("speed"), eta=d.get("eta"))

    def on_post(d):
        if d["status"] == "started":
            names = {"Merger": "Joining video and audio", "FFmpegExtractAudio": "Making the MP3"}
            if d.get("postprocessor") in names:
                job.update(stage="processing", label=names[d["postprocessor"]], percent=None, speed=None, eta=None)

    opts = {
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [on_progress],
        "postprocessor_hooks": [on_post],
        "noplaylist": True,
        "js_runtimes": JS,
        "age_limit": AGE_LIMIT,
        "format": pick_format(kind),
        # Highest resolution first; at equal resolution prefer H.264 + AAC, which
        # QuickTime plays (YouTube's 1440p/4K is VP9/AV1 only and gets converted)
        "format_sort": ["res", "vcodec:h264", "acodec:aac"],
        "outtmpl": os.path.join(tmp, "%(title).80s.%(ext)s"),
    }
    if HAS_FFMPEG:
        if kind == "audio":
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        else:
            opts["merge_output_format"] = "mp4"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = [os.path.join(tmp, f) for f in os.listdir(tmp)]
    if not files:
        raise RuntimeError("Nothing was downloaded")
    path = max(files, key=os.path.getsize)
    if HAS_FFMPEG and kind != "audio":
        path = make_playable(path, job)
    return tmp, path


# Codecs QuickTime (and iPhone) can play inside an MP4
OK_VIDEO = {"h264", "hevc"}
OK_AUDIO = {"aac", "mp3", "alac"}


def make_playable(path, job):
    """Convert to H.264/AAC MP4 if the download uses codecs QuickTime can't play."""
    height = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    height = int(height) if height.isdigit() else 1080
    # ~1.5x YouTube's own VP9 rates; 45M made a 78-min 4K lecture 26.7 GB
    bitrate = "24M" if height > 1440 else "12M" if height > 1080 else "6M"
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.split()
    codecs = [line.split(",") for line in out if "," in line]
    video = [c for c, t in codecs if t == "video"]
    audio = [c for c, t in codecs if t == "audio"]
    v_ok = all(c in OK_VIDEO for c in video)
    a_ok = all(c in OK_AUDIO for c in audio)
    if v_ok and a_ok and path.endswith(".mp4"):
        return path
    fixed = os.path.splitext(path)[0] + ".playable.mp4"
    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    duration = float(duration) if duration.replace(".", "", 1).isdigit() else 0
    job.update(stage="converting", label="Converting for QuickTime", percent=0, speed=None, eta=None)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1", "-i", path, "-map", "0:v:0?", "-map", "0:a:0?"]
    # Mac: fast hardware encoder. Elsewhere: x264, which every ffmpeg build has
    encoder = ["h264_videotoolbox", "-b:v", bitrate] if IS_MAC else ["libx264", "-preset", "veryfast", "-crf", "20"]
    cmd += ["-c:v", "copy"] if v_ok else ["-c:v", *encoder, "-tag:v", "avc1"]
    cmd += ["-c:a", "copy"] if a_ok else ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", fixed]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if line.startswith("out_time_us=") and duration:
            us = line.split("=")[1].strip()
            if us.isdigit():
                job["percent"] = round(min(100, int(us) / 1e6 / duration * 100), 1)
    if proc.wait():
        raise RuntimeError("Converting the video failed")
    os.remove(path)
    final = fixed.replace(".playable.mp4", ".mp4")
    os.rename(fixed, final)
    return final


def save(path):
    os.makedirs(OUT, exist_ok=True)
    name = os.path.basename(path)
    dest = os.path.join(OUT, name)
    base, ext = os.path.splitext(name)
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(OUT, f"{base} ({n}){ext}")
    shutil.move(path, dest)
    return os.path.basename(dest)


def run_job(job, url, kind):
    tmp = None
    try:
        tmp, path = fetch(url, kind, job)
        job.update(stage="done", label="Saved", percent=100, saved=save(path), speed=None, eta=None)
    except Exception as e:
        job.update(stage="error", error=clean(e))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# Phone mode: off until switched on from the computer; a second listener on the
# Wi-Fi address, guarded by a PIN. Everything resets when Haseed restarts.
PHONE = {"on": False, "pin": None, "tokens": set(), "fails": 0, "locked_until": 0, "url": None}


def lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("192.0.2.1", 9))  # no packet is sent; this just picks the Wi-Fi interface
        return s.getsockname()[0]


def phone_on():
    if PHONE["on"]:
        return
    ip = lan_ip()
    srv = ThreadingHTTPServer((ip, PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    PHONE.update(on=True, pin=f"{secrets.randbelow(10**6):06d}", url=f"http://{ip}:{PORT}")


def check_pin(pin):
    """Returns a login token, or None. Five wrong tries lock phones out for 10 minutes."""
    if time.time() < PHONE["locked_until"]:
        return None
    if PHONE["pin"] and secrets.compare_digest(pin, PHONE["pin"]):
        PHONE["fails"] = 0
        token = secrets.token_urlsafe(24)
        PHONE["tokens"].add(token)
        return token
    PHONE["fails"] += 1
    if PHONE["fails"] >= 5:
        PHONE.update(fails=0, locked_until=time.time() + 600)
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def is_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def phone_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "haseed" and v in PHONE["tokens"]:
                return v
        return None

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        local = self.is_local()
        # Phones may load the page and log in; everything else needs the PIN first
        if not local and u.path not in ("/", "/index.html", "/api/whoami", "/api/login") and not self.phone_token():
            return self._json(401, {"error": "Enter the PIN shown on your computer"})
        if u.path == "/api/whoami":
            info = {"local": local, "authed": local or bool(self.phone_token()), "app": IS_ANDROID_APP}
            if local:
                info["phone"] = {k: PHONE[k] for k in ("on", "pin", "url")}
            return self._json(200, info)
        if u.path == "/api/login":
            if local:
                return self._json(200, {"ok": True})
            token = check_pin(q.get("pin", ""))
            if not token:
                locked = time.time() < PHONE["locked_until"]
                return self._json(403, {"error": "Too many wrong tries. Wait 10 minutes." if locked else "Wrong PIN"})
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", f"haseed={token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if u.path == "/api/phone":
            if not local:
                return self._json(403, {"error": "Only from the computer"})
            try:
                phone_on()
            except OSError as e:
                return self._json(500, {"error": f"Couldn't open phone mode: {e}"})
            return self._json(200, {k: PHONE[k] for k in ("on", "pin", "url")})
        if u.path == "/api/file":
            path = os.path.join(OUT, os.path.basename(q.get("name", "")))
            if not os.path.isfile(path):
                return self._json(404, {"error": "That file is no longer in the Haseed folder"})
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4" if path.endswith(".mp4") else "application/octet-stream")
            self.send_header("Content-Length", str(os.path.getsize(path)))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(os.path.basename(path))}")
            self.end_headers()
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return
        if u.path in ("/", "/index.html"):
            with open(os.path.join(ROOT, "index.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/thumb":
            # Serve the thumbnail from our own address so the page may read its colours
            src = q.get("url", "")
            if urlparse(src).scheme not in ("http", "https"):
                return self._json(400, {"error": "bad thumbnail address"})
            try:
                with urlopen(Request(src, headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as r:
                    kind, body = r.headers.get("Content-Type", ""), r.read(5_000_000)
            except Exception as e:
                return self._json(502, {"error": clean(e)})
            if not kind.startswith("image/"):
                return self._json(415, {"error": "not an image"})
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/info":
            try:
                self._json(200, probe(q.get("url", "")))
            except Exception as e:
                self._json(400, {"error": clean(e)})
        elif u.path == "/api/start":
            job_id = uuid.uuid4().hex[:12]
            JOBS[job_id] = {"stage": "starting", "label": "Starting", "percent": 0}
            threading.Thread(target=run_job, args=(JOBS[job_id], q.get("url", ""), q.get("kind", "best")),
                             daemon=True).start()
            self._json(200, {"id": job_id})
        elif u.path == "/api/reveal":
            if not local:
                return self._json(403, {"error": "Only from the computer"})
            path = os.path.join(OUT, os.path.basename(q.get("name", "")))
            if not os.path.isfile(path):
                return self._json(404, {"error": "That file is no longer in the Haseed folder"})
            if IS_WIN:
                subprocess.run(["explorer", "/select,", path])
            elif IS_MAC:
                subprocess.run(["open", "-R", path])
            else:
                subprocess.run(["xdg-open", OUT])
            self._json(200, {"ok": True})
        elif u.path == "/api/progress":
            job = JOBS.get(q.get("id", ""))
            self._json(200 if job else 404, job or {"error": "unknown download"})
        else:
            self._json(404, {"error": "not found"})


def clean(e):
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")  # drop terminal colour codes
    return msg.split("; please report")[0][:300]


def main():
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        webbrowser.open(f"http://localhost:{PORT}")
        sys.exit(f"Haseed is already running at http://localhost:{PORT}")
    if not os.environ.get("HASEED_NO_BROWSER"):
        threading.Timer(1, webbrowser.open, [f"http://localhost:{PORT}"]).start()
    print(f"Haseed running on http://localhost:{PORT}  (ffmpeg: {'yes' if HAS_FFMPEG else 'no'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
