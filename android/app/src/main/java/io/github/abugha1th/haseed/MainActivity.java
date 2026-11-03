package io.github.abugha1th.haseed;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.os.Build;
import android.view.WindowInsets;
import android.widget.FrameLayout;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import com.yausername.ffmpeg.FFmpeg;
import com.yausername.youtubedl_android.YoutubeDL;

import java.io.File;
import java.net.HttpURLConnection;
import java.net.URL;

/** Runs Haseed's own server.py on the phone and shows its page full-screen. */
public class MainActivity extends Activity {
    private static final String HOME = "http://127.0.0.1:8788/";
    private static boolean serverStarted = false;
    private WebView web;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);  // remembers the chosen language
        web.setWebViewClient(new WebViewClient());
        web.setBackgroundColor(0xFF0A0E17);
        // Android 15 draws apps under the status and navigation bars; keep the page clear of them
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xFF0A0E17);
        root.addView(web);
        if (Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((v, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        setContentView(root);
        web.loadData("<body style='background:#0A0E17'></body>", "text/html", "utf-8");

        startServer();
        new Thread(() -> {
            waitForServer();
            new Handler(Looper.getMainLooper()).post(() -> web.loadUrl(pageFor(getIntent())));
        }).start();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        web.loadUrl(pageFor(intent));
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    /** A link shared from another app (YouTube, Instagram...) is handed to the page to look up. */
    private String pageFor(Intent intent) {
        if (intent != null && Intent.ACTION_SEND.equals(intent.getAction())) {
            String text = intent.getStringExtra(Intent.EXTRA_TEXT);
            if (text != null) {
                java.util.regex.Matcher m = java.util.regex.Pattern.compile("https?://\\S+").matcher(text);
                if (m.find()) return HOME + "?url=" + Uri.encode(m.group());
            }
        }
        return HOME;
    }

    private synchronized void startServer() {
        if (serverStarted) return;
        serverStarted = true;
        new Thread(() -> {
            try {  // unpacks ffmpeg and the libraries it needs on first run
                YoutubeDL.getInstance().init(getApplicationContext());
                FFmpeg.getInstance().init(getApplicationContext());
            } catch (Exception e) {
                android.util.Log.e("Haseed", "unpacking ffmpeg failed", e);
            }
            if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
            File out = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Haseed");
            Python.getInstance().getModule("haseed_android").callAttr("start",
                    getApplicationInfo().nativeLibraryDir,
                    new File(getNoBackupFilesDir(), "youtubedl-android/packages/ffmpeg/usr/lib").getPath()
                            + ":" + new File(getNoBackupFilesDir(), "youtubedl-android/packages/python/usr/lib").getPath(),
                    new File(getFilesDir(), "bin").getPath(),
                    out.getPath());
        }).start();
    }

    private static void waitForServer() {
        for (int i = 0; i < 600; i++) {  // up to a minute: the first start unpacks Python
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(HOME + "api/whoami").openConnection();
                c.setConnectTimeout(500);
                if (c.getResponseCode() == 200) return;
            } catch (Exception ignored) { }
            try { Thread.sleep(100); } catch (InterruptedException e) { return; }
        }
    }
}
