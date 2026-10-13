"""GitHub Actions CLI: source ZIP or Figma file URL -> debug APK."""
import os, re, shutil, subprocess, tempfile, urllib.request, zipfile
from pathlib import Path
from urllib.parse import urlparse
from app.main import extract_zip_safely, build_web_fallback, write_android_project, MAX_ZIP_BYTES

ROOT = Path.cwd()
OUT = ROOT / 'build-output'
OUT.mkdir(exist_ok=True)
APP_NAME = os.environ.get('APP_NAME', 'My Figma App')
PACKAGE_NAME = os.environ.get('PACKAGE_NAME', 'com.example.myfigmaapp')
ZIP_URL = os.environ.get('ZIP_URL', '').strip()
FIGMA_URL = os.environ.get('FIGMA_URL', '').strip()
FIGMA_TOKEN = os.environ.get('FIGMA_TOKEN', '').strip()


def fetch(url: str, headers=None, limit=MAX_ZIP_BYTES):
    if urlparse(url).scheme != 'https': raise RuntimeError('Only HTTPS source URLs are accepted.')
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'figtoapk/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit: raise RuntimeError('Source exceeds the configured download size limit.')
    return data


def figma_key(url: str) -> str:
    match = re.search(r'figma\.com/(?:file|design)/([A-Za-z0-9]+)', url)
    if not match: raise RuntimeError('Invalid Figma file link.')
    return match.group(1)


def walk_frames(node, out):
    if not isinstance(node, dict): return
    if node.get('type') in ('FRAME', 'COMPONENT', 'COMPONENT_SET'):
        out.append({'id': node.get('id'), 'name': node.get('name', 'Frame')})
    for child in node.get('children', []) or []: walk_frames(child, out)


def figma_zip(dest: Path):
    if not FIGMA_TOKEN: raise RuntimeError('Set the FIGMA_TOKEN repository secret to enable Figma link imports.')
    key = figma_key(FIGMA_URL)
    headers = {'X-Figma-Token': FIGMA_TOKEN, 'User-Agent': 'figtoapk/1.0'}
    import json
    meta = json.loads(fetch(f'https://api.figma.com/v1/files/{key}?depth=3', headers, 20 * 1024 * 1024))
    frames=[]; walk_frames(meta.get('document', {}), frames)
    frames = frames[:30]
    if not frames: raise RuntimeError('No frames/components found in this Figma file.')
    import urllib.parse
    ids = ','.join(x['id'] for x in frames)
    images = json.loads(fetch(f'https://api.figma.com/v1/images/{key}?ids={urllib.parse.quote(ids)}&format=png&scale=1', headers, 5 * 1024 * 1024))
    image_map = images.get('images', {})
    dest.mkdir(parents=True, exist_ok=True)
    for idx, frame in enumerate(frames):
        image_url = image_map.get(frame['id'])
        if not image_url: continue
        suffix = re.sub(r'[^A-Za-z0-9_-]+', '-', frame['name']).strip('-')[:55] or f'frame-{idx+1}'
        data = fetch(image_url, {'User-Agent': 'figtoapk/1.0'}, 15 * 1024 * 1024)
        (dest / f'{idx+1:02d}-{suffix}.png').write_bytes(data)
    if not list(dest.glob('*.png')): raise RuntimeError('Figma did not return frame exports. Check the file permissions and API token.')
    zpath = ROOT / 'figma-export.zip'
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in dest.glob('*.png'): zf.write(p, p.name)
    return zpath


def main():
    if bool(ZIP_URL) == bool(FIGMA_URL): raise RuntimeError('Provide exactly one source: ZIP_URL or FIGMA_URL.')
    with tempfile.TemporaryDirectory(prefix='figtoapk-build-') as tmp:
        tmp = Path(tmp)
        if ZIP_URL:
            raw = fetch(ZIP_URL)
            zpath = tmp / 'source.zip'; zpath.write_bytes(raw)
        else:
            zpath = figma_zip(tmp / 'figma-frames')
        extracted = tmp / 'input'; extracted.mkdir()
        files = extract_zip_safely(zpath.read_bytes(), extracted)
        webroot, mode = build_web_fallback(files, extracted)
        project = tmp / 'android'; project.mkdir()
        write_android_project(project, APP_NAME, PACKAGE_NAME, webroot)
        env = os.environ.copy()
        # Pin the selected SDK compile platform from workflow setup.
        proc = subprocess.run(['gradle', '--no-daemon', '--stacktrace', 'assembleDebug'], cwd=project, capture_output=True, text=True, timeout=900, env=env)
        if proc.returncode:
            print(proc.stdout[-5000:]); print(proc.stderr[-5000:]); raise RuntimeError('Gradle Android build failed.')
        apk = project / 'app/build/outputs/apk/debug/app-debug.apk'
        if not apk.exists(): raise RuntimeError('Gradle succeeded but APK output was missing.')
        shutil.copy2(apk, OUT / 'figtoapk.apk')
        print(f'APK ready. Conversion mode: {mode}.')

if __name__ == '__main__':
    main()
