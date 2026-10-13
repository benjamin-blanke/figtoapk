"""GitHub Actions CLI: source ZIP or Figma file URL -> debug APK."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from app.main import (
    MAX_ZIP_BYTES,
    build_web_fallback,
    extract_zip_safely,
    write_android_project,
)

ROOT = Path.cwd()
OUT = ROOT / "build-output"
OUT.mkdir(exist_ok=True)

APP_NAME = os.environ.get("APP_NAME", "My Figma App").strip()
PACKAGE_NAME = os.environ.get("PACKAGE_NAME", "com.example.myfigmaapp").strip()
ZIP_URL = os.environ.get("ZIP_URL", "").strip()
FIGMA_URL = os.environ.get("FIGMA_URL", "").strip()
FIGMA_TOKEN = os.environ.get("FIGMA_TOKEN", "").strip()


def fetch(url: str, headers=None, limit=MAX_ZIP_BYTES):
    parsed = urlparse(url)

    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("Only valid HTTPS source URLs are accepted.")

    req = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": "figtoapk/1.0"},
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        content_length = response.headers.get("Content-Length")

        if content_length and int(content_length) > limit:
            raise RuntimeError(
                "Source exceeds the configured download size limit."
            )

        data = response.read(limit + 1)

    if len(data) > limit:
        raise RuntimeError(
            "Source exceeds the configured download size limit."
        )

    return data


def validate_package_name(value: str):
    if len(value) > 150 or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+",
        value,
    ):
        raise RuntimeError(
            "Invalid Android package ID. Example: com.example.myapp"
        )


def figma_key(url: str) -> str:
    match = re.search(
        r"figma\.com/(?:file|design)/([A-Za-z0-9]+)",
        url,
    )

    if not match:
        raise RuntimeError("Invalid Figma file link.")

    return match.group(1)


def walk_frames(node, out):
    if not isinstance(node, dict):
        return

    if node.get("type") in ("FRAME", "COMPONENT", "COMPONENT_SET"):
        out.append(
            {
                "id": node.get("id"),
                "name": node.get("name", "Frame"),
            }
        )

    for child in node.get("children", []) or []:
        walk_frames(child, out)


def figma_zip(dest: Path):
    if not FIGMA_TOKEN:
        raise RuntimeError(
            "Set the FIGMA_TOKEN repository secret to enable Figma imports."
        )

    key = figma_key(FIGMA_URL)
    headers = {
        "X-Figma-Token": FIGMA_TOKEN,
        "User-Agent": "figtoapk/1.0",
    }

    metadata = json.loads(
        fetch(
            f"https://api.figma.com/v1/files/{key}?depth=3",
            headers,
            20 * 1024 * 1024,
        )
    )

    frames = []
    walk_frames(metadata.get("document", {}), frames)
    frames = frames[:30]

    if not frames:
        raise RuntimeError(
            "No frames/components found in this Figma file."
        )

    ids = ",".join(frame["id"] for frame in frames)
    query = urllib.parse.urlencode(
        {
            "ids": ids,
            "format": "png",
            "scale": "1",
        }
    )

    images = json.loads(
        fetch(
            f"https://api.figma.com/v1/images/{key}?{query}",
            headers,
            5 * 1024 * 1024,
        )
    )

    image_map = images.get("images", {})
    dest.mkdir(parents=True, exist_ok=True)

    for idx, frame in enumerate(frames):
        image_url = image_map.get(frame["id"])

        if not image_url:
            continue

        suffix = (
            re.sub(
                r"[^A-Za-z0-9_-]+",
                "-",
                frame["name"],
            ).strip("-")[:55]
            or f"frame-{idx + 1}"
        )

        data = fetch(
            image_url,
            {"User-Agent": "figtoapk/1.0"},
            15 * 1024 * 1024,
        )

        (dest / f"{idx + 1:02d}-{suffix}.png").write_bytes(data)

    exported_images = list(dest.glob("*.png"))

    if not exported_images:
        raise RuntimeError(
            "Figma did not return frame exports. "
            "Check file permissions and the API token."
        )

    zip_path = ROOT / "figma-export.zip"

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in exported_images:
            archive.write(path, path.name)

    return zip_path


def run_gradle(project: Path):
    command = [
        "gradle",
        "--no-daemon",
        "--stacktrace",
        "--console=plain",
        "assembleDebug",
    ]

    print("===== ANDROID PROJECT =====", flush=True)
    print(f"Project directory: {project}", flush=True)

    gradle_file = project / "app" / "build.gradle"

    print("===== GENERATED app/build.gradle =====", flush=True)
    print(gradle_file.read_text(encoding="utf-8"), flush=True)

    print("===== GRADLE BUILD START =====", flush=True)

    try:
        proc = subprocess.run(
            command,
            cwd=project,
            capture_output=True,
            text=True,
            timeout=900,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(exc.stdout, flush=True)
        if exc.stderr:
            print(exc.stderr, flush=True)

        raise RuntimeError(
            "Gradle build timed out after 15 minutes."
        ) from exc

    if proc.stdout:
        print("===== GRADLE STDOUT =====", flush=True)
        print(proc.stdout, flush=True)

    if proc.stderr:
        print("===== GRADLE STDERR =====", flush=True)
        print(proc.stderr, flush=True)

    if proc.returncode != 0:
        raise RuntimeError(
            f"Gradle Android build failed with exit code {proc.returncode}."
        )


def main():
    if bool(ZIP_URL) == bool(FIGMA_URL):
        raise RuntimeError(
            "Provide exactly one source: ZIP_URL or FIGMA_URL."
        )

    validate_package_name(PACKAGE_NAME)

    if not APP_NAME:
        raise RuntimeError("APP_NAME cannot be empty.")

    print(f"App name: {APP_NAME}", flush=True)
    print(f"Package name: {PACKAGE_NAME}", flush=True)

    with tempfile.TemporaryDirectory(
        prefix="figtoapk-build-"
    ) as tmp:
        tmp = Path(tmp)

        if ZIP_URL:
            print("Downloading source ZIP...", flush=True)
            raw = fetch(ZIP_URL)
            zip_path = tmp / "source.zip"
            zip_path.write_bytes(raw)
        else:
            print("Exporting Figma frames...", flush=True)
            zip_path = figma_zip(tmp / "figma-frames")

        extracted = tmp / "input"
        extracted.mkdir()

        print("Extracting source ZIP...", flush=True)
        files = extract_zip_safely(zip_path.read_bytes(), extracted)

        print(f"Extracted {len(files)} files.", flush=True)

        webroot, mode = build_web_fallback(files, extracted)
        print(f"Conversion mode: {mode}", flush=True)

        project = tmp / "android"
        project.mkdir()

        print("Generating Android project...", flush=True)
        write_android_project(
            project,
            APP_NAME,
            PACKAGE_NAME,
            webroot,
        )

        run_gradle(project)

        apk = (
            project
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "debug"
            / "app-debug.apk"
        )

        if not apk.is_file() or apk.stat().st_size == 0:
            raise RuntimeError(
                "Gradle finished but the APK is missing or empty."
            )

        output_apk = OUT / "figtoapk.apk"
        shutil.copy2(apk, output_apk)

        print(f"APK ready: {output_apk}", flush=True)
        print(f"APK size: {output_apk.stat().st_size} bytes", flush=True)
        print(f"Conversion mode: {mode}", flush=True)


if __name__ == "__main__":
    main()
