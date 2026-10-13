import { NextRequest, NextResponse } from 'next/server';
export const runtime = 'nodejs';
export const maxDuration = 15;
const PACKAGE_ID = /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/;
const isHttps = (value: string) => { try { return new URL(value).protocol === 'https:'; } catch { return false; } };
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const appName = String(body.appName || 'My Figma App').trim();
    const packageName = String(body.packageName || 'com.example.myfigmaapp').trim();
    const zipUrl = String(body.zipUrl || '').trim();
    const figmaUrl = String(body.figmaUrl || '').trim();
    if (!appName || appName.length > 50) return NextResponse.json({ error: 'App name must be between 1 and 50 characters.' }, { status: 400 });
    if (!PACKAGE_ID.test(packageName) || packageName.length > 150) return NextResponse.json({ error: 'Use a valid Android package ID, e.g. com.example.myapp.' }, { status: 400 });
    if (!!zipUrl === !!figmaUrl) return NextResponse.json({ error: 'Choose either an uploaded ZIP or a Figma file link.' }, { status: 400 });
    if (zipUrl && (!isHttps(zipUrl) || !zipUrl.includes('.public.blob.vercel-storage.com'))) return NextResponse.json({ error: 'Invalid uploaded ZIP URL.' }, { status: 400 });
    if (figmaUrl && (!isHttps(figmaUrl) || !/figma\.com\/(file|design)\//.test(figmaUrl))) return NextResponse.json({ error: 'Enter a valid Figma file or design link.' }, { status: 400 });
    const token = process.env.GITHUB_ACTIONS_TOKEN;
    const owner = process.env.GITHUB_OWNER;
    const repo = process.env.GITHUB_REPO;
    if (!token || !owner || !repo) return NextResponse.json({ error: 'GitHub Actions is not configured. Add GITHUB_ACTIONS_TOKEN, GITHUB_OWNER and GITHUB_REPO to Vercel.' }, { status: 503 });
    const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/actions/workflows/build-apk.yml/dispatches`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: 'main', inputs: { app_name: appName, package_name: packageName, zip_url: zipUrl, figma_url: figmaUrl } }),
    });
    if (!response.ok) {
      const detail = await response.text();
      return NextResponse.json({ error: response.status === 404 ? 'Workflow not found. Push the figtoapk project to GitHub and make sure build-apk.yml is on the main branch.' : `GitHub could not start the build (${response.status}). Check the token permissions. ${detail.slice(0, 220)}` }, { status: 502 });
    }
    return NextResponse.json({ ok: true, message: 'Build queued on GitHub Actions. Once it finishes, download the APK from the Releases page of your configured GitHub repository.', actionsUrl: `https://github.com/${owner}/${repo}/actions`, releasesUrl: `https://github.com/${owner}/${repo}/releases` });
  } catch {
    return NextResponse.json({ error: 'Could not start the GitHub Actions build. Check the Vercel logs and GitHub configuration.' }, { status: 502 });
  }
}
