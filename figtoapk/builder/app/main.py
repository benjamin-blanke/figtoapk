import io, os, re, shutil, subprocess, tempfile, uuid, zipfile
from pathlib import Path
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

app = FastAPI(title="figtoapk build worker", version="1.0.0")
TOKEN = os.getenv("FIGTOAPK_BUILDER_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
WORK_DIR = Path(os.getenv("FIGTOAPK_WORK_DIR", "/tmp/figtoapk"))
MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_UNPACKED_BYTES = 350 * 1024 * 1024
MAX_FILES = 2500
APK_DIR = WORK_DIR / "apks"
APK_DIR.mkdir(parents=True, exist_ok=True)


def check_auth(authorization: str | None):
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized build request")


def safe_package(value: str) -> str:
    if len(value) > 150 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+", value):
        raise HTTPException(status_code=400, detail="Invalid Android package ID")
    return value


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 _.-]", "", value).strip()
    return (value or "My Figma App")[:50]


def extract_zip_safely(raw: bytes, dest: Path) -> list[Path]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid ZIP archive")
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise HTTPException(status_code=413, detail="ZIP contains too many files")
    total = sum(x.file_size for x in infos)
    if total > MAX_UNPACKED_BYTES:
        raise HTTPException(status_code=413, detail="Uncompressed ZIP exceeds 350 MB")
    files = []
    root = dest.resolve()
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or any(part == ".." for part in name.split("/")):
            raise HTTPException(status_code=400, detail="ZIP contains an unsafe file path")
        # Symlinks can redirect writes outside the extraction root; do not extract them.
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise HTTPException(status_code=400, detail="ZIP symlinks are not accepted")
        target = (dest / name).resolve()
        if target != root and root not in target.parents:
            raise HTTPException(status_code=400, detail="ZIP contains an unsafe file path")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        files.append(target)
    return files


def build_web_fallback(files: list[Path], extracted: Path):
    """Use existing web entrypoint if present; otherwise create a clear asset gallery shell."""
    html_files = [p for p in files if p.name.lower() in ("index.html", "index.htm")]
    if html_files:
        # Prefer the shortest path to the entrypoint, then copy its containing directory into assets.
        entry = sorted(html_files, key=lambda p: len(p.relative_to(extracted).parts))[0]
        webroot = entry.parent
        return webroot, "web-export"
    supported = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
    assets = [p for p in files if p.suffix.lower() in supported]
    if not assets:
        raise HTTPException(status_code=422, detail="No index.html or supported design assets were found. Export a web prototype or include PNG/JPG/SVG assets in the ZIP.")
    webroot = extracted / "generated-web"
    webroot.mkdir(parents=True, exist_ok=True)
    # Keep paths relative to extraction root so nested asset directories remain grouped.
    cards = []
    generated_assets = webroot / "assets"
    generated_assets.mkdir(parents=True, exist_ok=True)
    for idx, p in enumerate(sorted(assets, key=lambda x: str(x).lower())[:250]):
        # Flatten asset names to avoid path traversal and preserve duplicate names safely.
        asset_name = f"asset-{idx}{p.suffix.lower()}"
        shutil.copy2(p, generated_assets / asset_name)
        title = p.stem.replace("-", " ").replace("_", " ").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cards.append(f'<article><img loading="lazy" src="assets/{asset_name}" alt="{title}"><div>{title}</div></article>')
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#101114"><title>Design preview</title><style>
*{box-sizing:border-box}body{margin:0;background:#101114;color:#f5f5f5;font:15px system-ui,sans-serif}header{padding:28px 22px;background:#191a20;border-bottom:1px solid #30313a}h1{font-size:24px;margin:0 0 8px}p{color:#a5a6b0;margin:0;line-height:1.5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;padding:18px}article{overflow:hidden;border:1px solid #30313a;border-radius:12px;background:#191a20}img{display:block;width:100%;height:180px;object-fit:contain;background:#22232a}article div{padding:10px 12px;font-size:12px;overflow-wrap:anywhere}</style></head><body><header><h1>Design preview</h1><p>Generated from uploaded design assets. For a faithful app, upload a working web export with index.html.</p></header><main class="grid">''' + "".join(cards) + "</main></body></html>"
    (webroot / "index.html").write_text(html, encoding="utf-8")
    return webroot, "asset-gallery-fallback"


def write_android_project(project: Path, app_name: str, package_name: str, webroot: Path):
    package_path = package_name.replace(".", "/")
    app_dir = project / "app"
    assets_dir = app_dir / "src" / "main" / "assets" / "www"
    java_dir = app_dir / "src" / "main" / "java" / package_path
    assets_dir.mkdir(parents=True, exist_ok=True)
    java_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(webroot, assets_dir, dirs_exist_ok=True)
    (project / "settings.gradle").write_text("pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\ndependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\nrootProject.name = 'FigtoApkBuild'\ninclude ':app'\n", encoding="utf-8")
    (project / "build.gradle").write_text("plugins { id 'com.android.application' version '8.7.3' apply false }\n", encoding="utf-8")
    (project / "gradle.properties").write_text("org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n", encoding="utf-8")
    (app_dir / "build.gradle").write_text(f'''plugins {{ id 'com.android.application' }}

android {{
    namespace '{package_name}'
    compileSdk 35
    defaultConfig {{ applicationId '{package_name}' minSdk 23 targetSdk 28 versionCode 1 versionName '1.0' }}
}}
''', encoding="utf-8")
    escaped_name = app_name.replace("\\", "\\\\").replace('"', '\\"')
    (app_dir / "src/main/AndroidManifest.xml").write_text(f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><uses-permission android:name="android.permission.INTERNET"/><application android:label="{escaped_name}" android:theme="@android:style/Theme.Material.Light.NoActionBar" android:usesCleartextTraffic="true"><activity android:name=".MainActivity" android:exported="true" android:configChanges="orientation|screenSize|keyboardHidden"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>''', encoding="utf-8")
    (java_dir / "MainActivity.java").write_text(f'''package {package_name};
import android.app.Activity; import android.os.Bundle; import android.webkit.WebView; import android.webkit.WebViewClient; import android.webkit.WebChromeClient; import android.webkit.WebSettings;
public class MainActivity extends Activity {{ private WebView webView; @Override public void onCreate(Bundle state) {{ super.onCreate(state); webView = new WebView(this); webView.setWebViewClient(new WebViewClient()); webView.setWebChromeClient(new WebChromeClient()); WebSettings settings = webView.getSettings(); settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true); settings.setAllowFileAccess(true); webView.loadUrl("file:///android_asset/www/index.html"); setContentView(webView); }} @Override public void onBackPressed() {{ if (webView != null && webView.canGoBack()) webView.goBack(); else super.onBackPressed(); }} }}''', encoding="utf-8")

@app.get("/health")
def health():
    return {"ok": True, "service": "figtoapk-builder"}

@app.post("/build")
async def build(file: UploadFile = File(...), appName: str = Form("My Figma App"), packageName: str = Form("com.example.myfigmaapp"), authorization: str | None = Header(default=None)):
    check_auth(authorization)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip file")
    package_name = safe_package(packageName)
    app_name = safe_name(appName)
    raw = await file.read(MAX_ZIP_BYTES + 1)
    if len(raw) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="ZIP exceeds 100 MB")
    build_id = uuid.uuid4().hex
    temp = Path(tempfile.mkdtemp(prefix="figtoapk-", dir=WORK_DIR))
    try:
        extracted = temp / "input"
        extracted.mkdir()
        files = extract_zip_safely(raw, extracted)
        webroot, mode = build_web_fallback(files, extracted)
        project = temp / "android"
        project.mkdir()
        write_android_project(project, app_name, package_name, webroot)
        proc = subprocess.run(["gradle", "--no-daemon", "--stacktrace", "assembleDebug"], cwd=project, capture_output=True, text=True, timeout=240)
        if proc.returncode != 0:
            tail = (proc.stderr + "\n" + proc.stdout)[-5000:]
            raise HTTPException(status_code=500, detail="Android build failed: " + tail)
        apk = project / "app/build/outputs/apk/debug/app-debug.apk"
        if not apk.exists():
            raise HTTPException(status_code=500, detail="Gradle finished but the APK was not found")
        saved = APK_DIR / f"{build_id}.apk"
        shutil.copy2(apk, saved)
        base = PUBLIC_BASE_URL or ""
        return {"downloadUrl": f"{base}/download/{build_id}" if base else f"/download/{build_id}", "buildId": build_id, "mode": mode, "message": "APK built successfully." if mode == "web-export" else "APK built with a generated design-asset preview. This is not a faithful reconstruction of the original Figma layout."}
    finally:
        shutil.rmtree(temp, ignore_errors=True)

@app.get("/download/{build_id}")
def download(build_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", build_id):
        raise HTTPException(status_code=404, detail="APK not found")
    apk = APK_DIR / f"{build_id}.apk"
    if not apk.exists():
        raise HTTPException(status_code=404, detail="APK not found or expired")
    return FileResponse(apk, media_type="application/vnd.android.package-archive", filename="figtoapk-app.apk")
