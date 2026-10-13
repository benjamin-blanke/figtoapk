# figtoapk — Figma / ZIP to Android APK

figtoapk uses **Vercel for the website**, **Vercel Blob for temporary ZIP storage**, and **GitHub Actions as the free build runner**. There is no separately managed build server in this version.

## Sources supported

- **Export ZIP:** upload a ZIP. It is stored in Vercel Blob and GitHub Actions downloads it to build the APK.
- **Figma file/design link:** GitHub Actions calls the Figma API, exports up to 30 frames as images, and creates an Android preview APK.

## Honest conversion behavior

- ZIP with `index.html`: the app packages that web export in an Android WebView, retaining the web export's behavior.
- ZIP with images but no `index.html`: the app creates an asset-gallery preview. It does **not** reconstruct the Figma layout faithfully.
- Figma link: frames/components are exported as PNGs and packaged into a preview APK. This is an image-based preview, not an automatic recreation of every Figma interaction, constraint, and responsive layout.

A real Figma design-to-code compiler is a separate, more complex capability. Exported frames alone don't contain enough executable application logic to reproduce every design automatically.

## Deploy

### 1. GitHub repository

1. Create a GitHub repository and push this project to its `main` branch.
2. Ensure Actions are enabled. The workflow is `.github/workflows/build-apk.yml`.
3. Create a fine-grained GitHub token for this repository with **Actions: Read and write** and **Contents: Read and write** permissions. The website uses it to dispatch builds.
4. For Figma imports, add repository secret `FIGMA_TOKEN` with a Figma personal access token that can read the target file.

### 2. Vercel

1. Import the same GitHub repository into Vercel.
2. In Vercel, create a **Blob** store under Storage and connect it to this project. This supplies `BLOB_READ_WRITE_TOKEN` for direct uploads.
3. Add these environment variables in Vercel Project Settings → Environment Variables:
   - `GITHUB_OWNER` — GitHub username or organization
   - `GITHUB_REPO` — repository name containing the workflow
   - `GITHUB_ACTIONS_TOKEN` — the fine-grained token described above
4. Redeploy after setting environment variables.

### 3. Run a test

Open the Vercel site, upload a ZIP or paste a Figma link, choose app name and package ID, then start the build. The site links to GitHub Actions for progress and GitHub Releases for the APK. The APK is a **debug build for testing**, not a Play Store release.

## Free-tier and privacy notes

GitHub Actions usage for public repositories is free under GitHub's standard policy; private repositories have plan quotas and limits. Vercel Blob has its own usage limits and pricing, so check the current Vercel plan before accepting large or frequent uploads. Uploaded ZIPs are stored in a public Blob URL in this starter because the workflow needs to fetch them; do not use it for confidential designs without changing the storage flow to private signed URLs and expiry/deletion.

Each build creates a public GitHub Release asset if the repository is public. Keep the repository private if designs or APKs must not be public, but then downloading releases may require GitHub authentication. For a public service, add abuse prevention, quotas, cleanup, access controls, and privacy terms before launch.

## Local development

```bash
npm install
npm run dev
```

The app requires a Vercel Blob store and the GitHub environment variables to submit real builds. The actual Android compilation runs in GitHub Actions, not inside Vercel Functions.
