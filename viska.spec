# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all necessary data files
datas = []
datas += collect_data_files('scipy')

# Hidden imports for PyQt6 and other dependencies
hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'scipy.io',
    'scipy.io.wavfile',
    'sounddevice',
    'pynput',
    'pynput.keyboard',
    'pynput.keyboard._darwin',
    'numpy',
    'openai',
    'dotenv',
    'httpx',
    'httpcore',
    'anyio',
    'sniffio',
    'certifi',
    'h11',
]

a = Analysis(
    ['wkey/gui_pyqt.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Viska',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch='universal2',
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Viska',
)

app = BUNDLE(
    coll,
    name='Viska.app',
    icon=None,  # Add path to .icns file here for custom icon
    bundle_identifier='com.viska.app',
    info_plist={
        'CFBundleName': 'Viska',
        'CFBundleDisplayName': 'Viska',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSMicrophoneUsageDescription': 'Viska needs microphone access to record your voice for transcription.',
        'NSAppleEventsUsageDescription': 'Viska needs accessibility access to type transcribed text into other applications.',
        'NSInputMonitoringUsageDescription': 'Viska needs input monitoring access to detect when you press the hotkey to start recording.',
        'LSUIElement': False,
        'NSHighResolutionCapable': True,
        'LSArchitecturePriority': ['arm64', 'x86_64'],
    },
)
