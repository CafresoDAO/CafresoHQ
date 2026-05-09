/**
 * CafresoAI — Electron main process
 *
 * Startup sequence:
 *   1. Single-instance lock (second launch focuses existing window)
 *   2. Detect Python 3 (offer download if missing)
 *   3. Check if port 8787 is already bound (server already running → skip spawn)
 *   4. Start serve.py in the background with windowsHide:true
 *   5. Show a branded loading splash while polling the HTTP server
 *   6. Navigate the main BrowserWindow to the app URL
 *   7. Install a system-tray icon so the app persists after window close
 */

const {
  app, BrowserWindow, Tray, Menu, nativeImage,
  shell, dialog, ipcMain,
} = require('electron');
const { spawn, execFileSync } = require('child_process');
const path  = require('path');
const net   = require('net');
const http  = require('http');
const fs    = require('fs');

// ─── Constants ────────────────────────────────────────────────────────────────
const PORT    = 8787;
const APP_URL = `http://localhost:${PORT}/hq.html`;
const PYTHON_DOWNLOAD_URL = 'https://www.python.org/downloads/windows/';
const MIN_PYTHON_MAJOR = 3;
const MIN_PYTHON_MINOR = 9;

// ─── State ────────────────────────────────────────────────────────────────────
let mainWindow   = null;
let loadingWin   = null;
let tray         = null;
let serverProc   = null;
app.isQuitting   = false;

// ─── Python detection ─────────────────────────────────────────────────────────
function findPython() {
  // On Windows the `py` launcher respects version constraints and is always
  // in PATH after a standard install.  Fall back to direct names.
  const candidates = ['py', 'python', 'python3'];
  for (const cmd of candidates) {
    try {
      // python --version prints to stdout (3.x) or stderr (2.x quirk)
      let out = '';
      try { out = execFileSync(cmd, ['--version'], { encoding: 'utf8', timeout: 4000 }); }
      catch (e) { out = (e.stderr || '') + (e.stdout || ''); }
      const m = out.match(/Python (\d+)\.(\d+)/);
      if (m) {
        const [, maj, min] = m.map(Number);
        if (maj >= MIN_PYTHON_MAJOR && min >= MIN_PYTHON_MINOR) {
          console.log(`[openclaw] Python found: ${cmd} (${maj}.${min})`);
          return cmd;
        }
      }
    } catch (_) { /* not on PATH */ }
  }
  return null;
}

// ─── Port probe ───────────────────────────────────────────────────────────────
function isPortBound(port) {
  return new Promise(resolve => {
    const s = net.createServer();
    s.once('error', () => resolve(true));          // EADDRINUSE → already bound
    s.once('listening', () => { s.close(); resolve(false); });
    s.listen(port, '127.0.0.1');
  });
}

// ─── Poll until server responds ───────────────────────────────────────────────
function waitForServer(url, timeoutMs = 25000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    function poll() {
      http.get(url, res => {
        res.resume();   // drain response body
        if (res.statusCode < 500) return resolve();
        retry();
      }).on('error', retry);
    }
    function retry() {
      if (Date.now() > deadline) return reject(new Error('Server did not start in time.'));
      setTimeout(poll, 350);
    }
    poll();
  });
}

// ─── Paths ────────────────────────────────────────────────────────────────────
function getServeDir() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app-files');
  }
  // Dev: electron/ is one level below the project root
  return path.resolve(__dirname, '..');
}

function getIconPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app-files', 'build', 'icon.png');
  }
  return path.join(__dirname, 'build', 'icon.png');
}

function getTrayIcon() {
  const p = getIconPath();
  if (fs.existsSync(p)) {
    const img = nativeImage.createFromPath(p);
    return img.resize({ width: 16, height: 16 });
  }
  // Fallback: empty 16×16 transparent image so Tray construction never throws
  return nativeImage.createEmpty();
}

// ─── Server start ─────────────────────────────────────────────────────────────
async function startServer() {
  // Skip if port is already in use (user ran serve.py manually, or double-launched)
  if (await isPortBound(PORT)) {
    console.log('[openclaw] Port already bound — skipping server spawn');
    return;
  }

  const python = findPython();
  if (!python) {
    const { response } = await dialog.showMessageBox({
      type: 'error',
      title: 'Python 3 Required',
      message: `CafresoAI needs Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+`,
      detail:
        'Python was not found on your system.\n\n' +
        '1. Download Python from python.org\n' +
        '2. During install, check "Add Python to PATH"\n' +
        '3. Restart CafresoAI',
      buttons: ['Download Python', 'Quit'],
      defaultId: 0,
    });
    if (response === 0) shell.openExternal(PYTHON_DOWNLOAD_URL);
    app.quit();
    return false;
  }

  const serveDir = getServeDir();
  const servePy  = path.join(serveDir, 'serve.py');

  if (!fs.existsSync(servePy)) {
    dialog.showErrorBox('Missing File', `Could not find:\n${servePy}`);
    app.quit();
    return false;
  }

  console.log(`[openclaw] Starting: ${python} ${servePy}`);

  serverProc = spawn(python, [servePy], {
    cwd: serveDir,
    windowsHide: true,
    env: {
      ...process.env,
      // Override hardcoded memory path so a new user gets a clean slate
      // in their own AppData rather than hitting Anthony's path.
      OPENCLAW_HQ_STATE_DIR: path.join(app.getPath('userData'), 'hq-state'),
    },
  });

  serverProc.stdout.on('data', d => process.stdout.write('[server] ' + d));
  serverProc.stderr.on('data', d => process.stderr.write('[server] ' + d));
  serverProc.on('exit', code => {
    console.log(`[server] exited (${code})`);
    serverProc = null;
  });

  return true;
}

// ─── Loading splash ───────────────────────────────────────────────────────────
const LOADING_HTML = `<!DOCTYPE html><html><head>
<meta charset="utf-8"/>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background: #fff8ee;
    font-family: 'Courier New', monospace;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100vh; user-select: none; -webkit-app-region: drag;
  }
  .logo { font-size: 56px; animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.08)} }
  h1 { margin-top: 14px; font-size: 15px; letter-spacing: .18em;
       color: #3b2e2a; font-weight: 900; text-transform: uppercase; }
  p  { margin-top: 8px; font-size: 11px; color: #7a6358; letter-spacing: .08em; }
  .dots { display: inline-block; width: 24px; }
  .bar {
    margin-top: 28px; width: 160px; height: 4px;
    background: #e8d8c0; border-radius: 2px; overflow: hidden;
  }
  .fill {
    height: 100%; width: 0; background: #daa520; border-radius: 2px;
    animation: grow 2s ease-in-out infinite;
  }
  @keyframes grow { 0%{width:0} 60%{width:100%} 100%{width:100%} }
</style></head><body>
  <div class="logo">🦞</div>
  <h1>CafresoAI</h1>
  <p>Starting server<span class="dots" id="d">...</span></p>
  <div class="bar"><div class="fill"></div></div>
  <script>
    let i=0;const d=document.getElementById('d');
    setInterval(()=>{i=(i+1)%4;d.textContent='.'.repeat(i)||'...'}, 400);
  </script>
</body></html>`;

function createLoadingWindow() {
  loadingWin = new BrowserWindow({
    width: 360, height: 280,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    center: true,
    backgroundColor: '#fff8ee',
    webPreferences: { nodeIntegration: false },
  });
  loadingWin.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(LOADING_HTML));
}

// ─── Main window ──────────────────────────────────────────────────────────────
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280, height: 820,
    minWidth: 375, minHeight: 600,
    title: 'CafresoAI',
    backgroundColor: '#fff8ee',
    show: false,
    icon: getIconPath(),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false,   // allow localhost assets
    },
  });

  mainWindow.loadURL(APP_URL);

  mainWindow.once('ready-to-show', () => {
    if (loadingWin && !loadingWin.isDestroyed()) loadingWin.close();
    loadingWin = null;
    mainWindow.show();
  });

  // Close to tray instead of quitting
  mainWindow.on('close', e => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
      if (tray) {
        tray.displayBalloon?.({
          title: 'CafresoAI',
          content: 'Still running in the system tray. Right-click the tray icon to quit.',
          iconType: 'info',
        });
      }
    }
  });

  mainWindow.on('closed', () => { mainWindow = null; });

  // Redirect external links to the system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(`http://localhost:${PORT}`)) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });
}

// ─── System tray ─────────────────────────────────────────────────────────────
function createTray() {
  tray = new Tray(getTrayIcon());
  tray.setToolTip('CafresoAI');

  const rebuild = () => tray.setContextMenu(Menu.buildFromTemplate([
    { label: '🦞  CafresoAI', enabled: false },
    { type: 'separator' },
    {
      label: 'Open Window',
      click() {
        if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
        else createMainWindow();
      },
    },
    {
      label: 'Open in Browser',
      click() { shell.openExternal(APP_URL); },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click() { app.isQuitting = true; app.quit(); },
    },
  ]));

  rebuild();

  tray.on('double-click', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
    else createMainWindow();
  });
}

// ─── App lifecycle ────────────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  // Second instance — focus the first and exit
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); }
  });

  app.whenReady().then(async () => {
    createLoadingWindow();

    const serverOk = await startServer();
    if (serverOk === false) return; // quit already triggered

    try {
      await waitForServer(APP_URL, 25000);
    } catch (err) {
      if (loadingWin && !loadingWin.isDestroyed()) loadingWin.close();
      const { response } = await dialog.showMessageBox({
        type: 'error',
        title: 'Server Timeout',
        message: 'CafresoAI server did not respond within 25 seconds.',
        detail: err.message + '\n\nCheck that Python 3 is in PATH and port 8787 is not blocked.',
        buttons: ['Retry', 'Quit'],
      });
      if (response === 0) { app.relaunch(); }
      app.quit();
      return;
    }

    createMainWindow();
    createTray();
  });

  app.on('window-all-closed', e => {
    // On Windows/Linux keep running in the tray
    e.preventDefault();
  });

  app.on('activate', () => {
    // macOS: re-open window on dock click
    if (!mainWindow) createMainWindow();
  });

  app.on('before-quit', () => {
    app.isQuitting = true;
    if (serverProc) {
      serverProc.kill();
      serverProc = null;
    }
  });
}
