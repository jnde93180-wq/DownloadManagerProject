# PowerShell helper to build the exe with PyInstaller.
# Usage: Run in PowerShell with your venv activated.
# You may need to edit $pyside_plugins to point to your PySide6 plugins folder.

param(
    [string]$spec = "download_manager.spec"
)

# Ensure PyInstaller installed:
pip install pyinstaller

# Try to locate PySide6 plugins automatically
$pyside = python -c "import PySide6; import os, sys; print(os.path.join(os.path.dirname(PySide6.__file__), 'plugins'))"
$pyside_plugins = $pyside.Trim()
Write-Host "Detected PySide6 plugins at: $pyside_plugins"

# Build
pyinstaller $spec

# Copy Qt plugins (if needed)
if (Test-Path $pyside_plugins) {
    $distDir = Join-Path -Path "dist" -ChildPath "DownloadManager"
    if (Test-Path $distDir) {
        Write-Host "Copying Qt plugins..."
        Copy-Item -Path (Join-Path $pyside_plugins "*") -Destination (Join-Path $distDir "plugins") -Recurse -Force
    }
}
Write-Host "Build complete. Check the dist folder."
