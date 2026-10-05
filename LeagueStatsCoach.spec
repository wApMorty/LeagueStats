# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['lol_coach.py'],
    pathex=[],
    binaries=[],
    # Client LeagueStats (SPEC-21) : gabarits et statiques (polices comprises), lus par
    # `config.get_resource_path("src/client/...")` ; aucun `hiddenimports` pour uvicorn ni pywebview.
    datas=[
        ('data/db.db', '.'),
        ('README.md', '.'),
        ('src/client/templates', 'src/client/templates'),
        ('src/client/static', 'src/client/static'),
    ],
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
    a.binaries,
    a.datas,
    [],
    name='LeagueStatsCoach',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
