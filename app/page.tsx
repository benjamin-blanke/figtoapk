'use client';
import { upload } from '@vercel/blob/client';
import { useRef, useState } from 'react';

type SourceMode = 'zip' | 'figma';
export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<SourceMode>('zip');
  const [file, setFile] = useState<File | null>(null);
  const [figmaUrl, setFigmaUrl] = useState('');
  const [appName, setAppName] = useState('My Figma App');
  const [packageName, setPackageName] = useState('com.example.myfigmaapp');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [links, setLinks] = useState<{actionsUrl?: string; releasesUrl?: string}>({});

  function chooseFile(next?: File) {
    setMessage(''); setError(false); setLinks({});
    if (!next) return;
    if (!next.name.toLowerCase().endsWith('.zip')) { setFile(null); setError(true); setMessage('Please choose a .zip file.'); return; }
    if (next.size > 100 * 1024 * 1024) { setFile(null); setError(true); setMessage('The ZIP is too large. Maximum size: 100 MB.'); return; }
    setFile(next);
  }

  async function convert() {
    if (mode === 'zip' && !file) { setError(true); setMessage('Upload your Figma export ZIP first.'); return; }
    if (mode === 'figma' && !/https:\/\/(www\.)?figma\.com\/(file|design)\//.test(figmaUrl)) { setError(true); setMessage('Paste a valid Figma file or design link.'); return; }
    setBusy(true); setError(false); setLinks({}); setMessage(mode === 'zip' ? 'Uploading your ZIP securely…' : 'Starting Figma import…');
    try {
      let zipUrl = '';
      if (mode === 'zip' && file) {
        const blob = await upload(file.name, file, {
          access: 'public', handleUploadUrl: '/api/blob-upload',
          onUploadProgress: (event) => setMessage(`Uploading ZIP… ${Math.round(event.percentage)}%`),
        });
        zipUrl = blob.url;
      }
      setMessage('Starting Android build on GitHub Actions…');
      const response = await fetch('/api/convert', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ zipUrl, figmaUrl: mode === 'figma' ? figmaUrl : '', appName, packageName }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not start build.');
      setMessage(result.message || 'Build queued.');
      setLinks({ actionsUrl: result.actionsUrl, releasesUrl: result.releasesUrl });
    } catch (e) { setError(true); setMessage(e instanceof Error ? e.message : 'Something went wrong.'); }
    finally { setBusy(false); }
  }

  return <main>
    <nav className="nav"><a className="brand" href="#"><span className="brand-icon">f</span> figtoapk</a><a className="nav-link" href="#how">How it works <span>↗</span></a></nav>
    <section className="hero"><div className="eyebrow"><span className="live-dot"/> DESIGN IN. ANDROID OUT.</div>
      <h1>Your design.<br/><span>Your Android app.</span></h1>
      <p className="subtitle">Start with a Figma design or exported ZIP. Build an Android APK without running your own server.</p>
      <div className="workspace"><div className="workspace-top"><div className="window-dots"><i/><i/><i/></div><span>NEW ANDROID BUILD</span><span className="secure"><span>✳</span> GITHUB ACTIONS BUILDER</span></div>
        <div className="workspace-body"><div className="source-panel">
          <div className="mode-tabs"><button className={mode === 'zip' ? 'mode-tab active' : 'mode-tab'} onClick={() => {setMode('zip');setMessage('');setError(false);}}>Upload ZIP</button><button className={mode === 'figma' ? 'mode-tab active' : 'mode-tab'} onClick={() => {setMode('figma');setMessage('');setError(false);}}>Figma link</button></div>
          {mode === 'zip' ? <div className={'dropzone ' + (file ? 'has-file' : '')} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault();chooseFile(e.dataTransfer.files?.[0]);}}>
            <input ref={inputRef} type="file" accept=".zip,application/zip" hidden onChange={e => chooseFile(e.target.files?.[0])}/>
            <div className="upload-icon">{file ? '✓' : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 15.5v3A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5v-3"/></svg>}</div>
            <strong>{file ? file.name : 'Drop your ZIP right here'}</strong><p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Ready to upload` : 'Upload exported design assets or a web-ready prototype'}</p>
            <button className="browse" onClick={() => inputRef.current?.click()}>{file ? 'Choose another file' : 'Browse files'} <span>↗</span></button><small>ZIP FILES ONLY · UP TO 100 MB</small>
          </div> : <div className="figma-input-panel"><div className="upload-icon figma-icon">F</div><strong>Paste your Figma file link</strong><p>Use a Figma file or design URL. The GitHub workflow will export available frames.</p><input value={figmaUrl} onChange={e => setFigmaUrl(e.target.value)} placeholder="https://www.figma.com/design/…"/><small>THE FIGMA API TOKEN IS STORED AS A GITHUB SECRET</small></div>}
        </div>
        <div className="fields"><label>APP NAME<input value={appName} maxLength={50} onChange={e => setAppName(e.target.value)} placeholder="My Figma App"/></label>
          <label>ANDROID PACKAGE ID<input value={packageName} maxLength={150} onChange={e => setPackageName(e.target.value)} placeholder="com.example.myapp"/></label>
          <div className="build-note"><span className="note-icon">⌘</span><div><b>Build on GitHub Actions</b><p>GitHub compiles the Android app. A Figma API token is needed for Figma links. ZIPs are temporarily stored in Vercel Blob.</p></div></div>
          <button className="convert" disabled={busy} onClick={convert}>{busy ? <><span className="spinner"/> Working…</> : <>Build my APK <span>→</span></>}</button>
          {message && <div className={'message ' + (error ? 'error' : '')} role="status">{message}{links.actionsUrl && <div className="result-links"><a href={links.actionsUrl} target="_blank" rel="noreferrer">View build progress ↗</a><a href={links.releasesUrl} target="_blank" rel="noreferrer">Download APK from Releases ↗</a></div>}</div>}
          <p className="fineprint">Only upload projects you own or have permission to use.</p>
        </div></div></div>
      <div className="trust-row"><span>✦ Made for makers</span><span>↗ No self-managed server</span><span>◈ Your design, your app</span></div>
    </section>
    <section className="how" id="how"><div className="section-kicker">THE SHORT VERSION</div><h2>From design to install.</h2><div className="steps">
      <article><span className="step-num">01</span><div className="step-icon">↑</div><h3>Upload or paste a link</h3><p>Use a ZIP export or give figtoapk a Figma file link with API access enabled.</p></article>
      <article><span className="step-num">02</span><div className="step-icon">⌘</div><h3>Build in the cloud</h3><p>GitHub Actions exports design frames or packages a web export and compiles the Android project.</p></article>
      <article><span className="step-num">03</span><div className="step-icon">↓</div><h3>Download the APK</h3><p>Find the APK attached to the build's GitHub Release when the workflow completes.</p></article>
    </div></section>
    <footer><a className="brand" href="#"><span className="brand-icon">f</span> figtoapk</a><span>From pixels to pocket.</span><span>© {new Date().getFullYear()} figtoapk</span></footer>
  </main>;
}
