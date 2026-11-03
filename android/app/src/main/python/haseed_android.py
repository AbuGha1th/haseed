"""Starts Haseed's server inside the Android app (called from MainActivity)."""
import os
import threading


def start(native_dir, ffmpeg_lib_dir, bin_dir, out_dir):
    """ffmpeg_lib_dir may list several folders, separated by ":"."""
    # Android only runs programs from the app's native library folder, so ffmpeg and
    # ffprobe live there as lib*.so; links named ffmpeg/ffprobe let yt-dlp find them.
    os.makedirs(bin_dir, exist_ok=True)
    for name in ("ffmpeg", "ffprobe", "qjs"):
        link = os.path.join(bin_dir, name)
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(os.path.join(native_dir, f"lib{name}.so"), link)
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ffmpeg_lib_dir  # the libraries ffmpeg links against
    os.environ["HASEED_OUT"] = out_dir
    os.environ["HASEED_ANDROID"] = "1"
    os.environ["HASEED_NO_BROWSER"] = "1"

    import subprocess
    try:  # one line in the log saying whether ffmpeg actually runs
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=20)
        print("ffmpeg check:", r.returncode, (r.stdout or r.stderr).splitlines()[:1])
    except Exception as e:
        print("ffmpeg check failed:", repr(e))

    from haseed import server  # imported after PATH is set, so it finds ffmpeg

    server.JS["quickjs"] = {"path": os.path.join(bin_dir, "qjs")}  # YouTube needs a JS runtime

    save = server.save

    def save_and_show_in_gallery(path):
        name = save(path)
        from java import jclass
        app = jclass("com.chaquo.python.Python").getPlatform().getApplication()
        jclass("android.media.MediaScannerConnection").scanFile(app, [os.path.join(server.OUT, name)], None, None)
        return name

    server.save = save_and_show_in_gallery
    threading.Thread(target=server.main, daemon=True).start()
