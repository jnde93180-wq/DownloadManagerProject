"""
Portable build helper: runs PyInstaller using the spec and copies PySide6 plugins
into the dist folder so the built exe can run on Windows.

Usage:
    python build_portable.py

This script expects PyInstaller installed in the active environment.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SPEC = "download_manager.spec"
DIST_NAME = "DownloadManager"


def find_pyside_plugins():
    try:
        import PySide6
        p = Path(PySide6.__file__).parent / "plugins"
        if p.exists():
            return p
    except Exception:
        pass
    return None


def main():
    # ensure pyinstaller installed
    try:
        import PyInstaller  # noqa: F401
    except Exception:
        print("PyInstaller not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"]) 

    # run pyinstaller
    print("Running PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "PyInstaller", SPEC])

    plugins_src = find_pyside_plugins()
    if not plugins_src:
        print("Could not locate PySide6 plugins automatically. If build fails, set plugins manually.")
        return

    dist_dir = Path("dist") / DIST_NAME
    if not dist_dir.exists():
        print(f"Dist folder {dist_dir} not found. Build may have failed.")
        return

    dest_plugins = dist_dir / "plugins"
    print(f"Copying PySide6 plugins from {plugins_src} to {dest_plugins}")
    if dest_plugins.exists():
        shutil.rmtree(dest_plugins)
    shutil.copytree(plugins_src, dest_plugins)
    print("Build complete. Check the dist folder.")


if __name__ == '__main__':
    main()
