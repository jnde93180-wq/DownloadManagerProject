# PyInstaller spec for building the app (may need adjustments for PySide6 plugins)
block_cipher = None
a = Analysis(['main.py'],
             pathex=[],
             binaries=[],
             datas=[('chrome-extension/*', 'chrome-extension'), ('plugins/*', 'plugins')],
             hiddenimports=['pyqtgraph', 'qasync', 'aiosqlite', 'aiohttp'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[])
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DownloadManager', debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True, name='DownloadManager')
