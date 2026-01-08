# Download Manager — Test Project (Windows)

This folder contains a runnable prototype of the Download Manager. Copy the files into a single folder and open that folder in your IDE (VS Code, PyCharm, etc).

What is included
- main.py — the GUI application (PySide6, asyncio)
- requirements.txt — Python dependencies
- test_server.py — lightweight local HTTP server to test segmented downloads (streams a large pseudo-file)
- download_manager.spec — PyInstaller spec example
- build_windows.ps1 — PowerShell helper script to build an .exe (adjust Qt plugin paths)
- chrome-extension/ — example browser extension files
- plugins/example_plugin.py — example plugin
- .vscode/launch.json — optional VSCode run configuration

Quick start (import to IDE and run)
1. Open your IDE and open the project folder (DownloadManagerProject).
2. Create a virtual environment (recommended):
   - In PowerShell:
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
   - In CMD:
     python -m venv .venv
     .\.venv\Scripts\activate.bat
3. Install dependencies:
     pip install -r requirements.txt

   Required packages:
   - PySide6
   - qasync
   - aiohttp
   - aiosqlite
   - pyqtgraph
   - yarl

   Optional (for torrent support):
   - python-libtorrent (libtorrent) — install only if you need torrent features.

4. (Optional) Run the test HTTP server in a separate terminal to have a fast local endpoint for testing segmented downloads:
     python test_server.py
   Server will run on http://127.0.0.1:8080 and expose `/large` which streams ~200 MB of data on the fly.

5. Run the GUI app:
     python main.py

   - Use "Add Download" to add a URL (for example, `http://127.0.0.1:8080/large` to test segmented downloads).
   - You can use the Add dialog to configure auth (unused for the test server), per-download bandwidth cap, segments, checksum (leave blank), schedule, and retries.
   - The app persists queue to `downloads.db` in the project folder.

Testing notes
- The test server streams deterministic data; use `http://127.0.0.1:8080/large` as a test URL.
- Clipboard monitoring: copy a URL (http/https/magnet) and the app will offer to add it.
- Browser extension: open the `chrome-extension` folder, load it as an unpacked extension in Chrome/Edge (developer mode). Clicking the extension will POST the current tab URL to the app's /add endpoint (127.0.0.1:8765). The app serves that endpoint automatically on startup.

Packaging to an .exe (optional)
- Install PyInstaller:
    pip install pyinstaller

- Adjust `download_manager.spec` if needed, especially to include PySide6 Qt plugin folders on Windows (platforms, imageformats).
- Run the included helper (PowerShell):
    ./build_windows.ps1
  The script runs PyInstaller and attempts to copy Qt plugins; you may need to tweak the Qt plugin path depending on your environment.

If you want, I can:
- Generate an installer script (NSIS) or create a build artifact and walk you through packaging.
- Provide small tweaks for your IDE (PyCharm run configurations, .idea folder).

Troubleshooting
- If PySide6 GUI fails to show or Qt plugins missing error occurs, run:
    python -c "import PySide6; import os, sys; print(os.path.join(os.path.dirname(PySide6.__file__), 'plugins'))"
  Then locate the PySide6 plugins folder and add it with --add-data when running PyInstaller (or adjust the PowerShell build script).
