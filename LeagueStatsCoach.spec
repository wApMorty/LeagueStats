# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs

# Collect native C extensions for PostgreSQL async drivers
asyncpg_binaries = collect_dynamic_libs('asyncpg')
greenlet_binaries = collect_dynamic_libs('greenlet')

a = Analysis(
    ['lol_coach.py'],
    pathex=[],
    binaries=asyncpg_binaries + greenlet_binaries,
    datas=[('data/db.db', '.'), ('README.md', '.')],
    hiddenimports=[
        # PostgreSQL async support (T18: PostgreSQL Direct Mode)
        'sqlalchemy.ext.asyncio',
        'asyncpg',
        'greenlet._greenlet',
    ],
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
