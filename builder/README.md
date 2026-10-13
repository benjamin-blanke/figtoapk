# Android build implementation

`build_cli.py` is the command-line entry point used by `.github/workflows/build-apk.yml`. It accepts either a ZIP URL or a Figma design URL, then generates an Android WebView project and builds a debug APK using Gradle.

The FastAPI service in `app/main.py` is retained as an optional legacy/self-hosted path; the default deployment in this repository does not require it.

Figma URL mode requires a `FIGMA_TOKEN` GitHub repository secret. It exports frames as PNG images. ZIP mode prefers an existing `index.html`; otherwise it makes an asset gallery from supported images. An image gallery is a preview and not a faithful reconstruction of a Figma design.
