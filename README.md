# Haseed (حصيد)

[العربية](README.ar.md)

Paste a link, get the file. Haseed is a small page that runs on your own computer and downloads videos from YouTube, Instagram, TikTok, X, Facebook and [over a thousand other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md), using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

- Pick the quality: every size the video has, up to 4K, or MP3
- Live progress while it downloads
- Files play in QuickTime and on iPhone: anything else is converted to H.264
- Saved to a **Haseed** folder on your Desktop
- English and Arabic interface (switch in the top corner)
- Nothing is uploaded anywhere, and there are no ads or accounts

## Run it

You need [Python 3](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** while installing.

1. Download this repo (green **Code** button → **Download ZIP**) and unzip it.
2. Start it:
   - **Mac:** double-click `start.command`. The first time, right-click it → **Open** to get past the security prompt.
   - **Windows:** double-click `start.bat`.
3. Your browser opens Haseed at http://localhost:8788. Keep the window open while you use it, and close it to stop.

The first start takes a minute while it installs what it needs (yt-dlp, ffmpeg and Deno) into a `.venv` folder inside the project. Each later start checks for a newer yt-dlp, because sites change often and older versions stop working.

## Good to know

- Haseed only listens on your own computer (`127.0.0.1`), so nobody else can reach it.
- Download only what you have the right to keep. Some sites' terms forbid downloading, and you are responsible for how you use this.
- Haseed is not affiliated with yt-dlp. Report download problems for a specific site to Haseed first, not to yt-dlp.
