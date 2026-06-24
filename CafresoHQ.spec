# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['serve.py'],
    pathex=[],
    binaries=[],
    datas=[('hq.html', '.'), ('app.jsx', '.'), ('views.jsx', '.'), ('ui.jsx', '.'), ('styles.css', '.'), ('features.jsx', '.'), ('missions.jsx', '.'), ('modals.jsx', '.'), ('tweaks-panel.jsx', '.'), ('sprites.jsx', '.'), ('mock-data.jsx', '.'), ('claude-client.jsx', '.'), ('agent_runner.jsx', '.'), ('manifest.webmanifest', '.'), ('sw.js', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CafresoHQ',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CafresoHQ',
)
