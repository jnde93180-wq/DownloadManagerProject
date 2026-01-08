import os
import zipfile
import urllib.request
import shutil
import glob

URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
ZIP_NAME = "ffmpeg.zip"
EXTRACT_DIR = "ffmpeg_temp"
TARGET_DIR = "ffmpeg"

def install():
    print(f"Downloading {URL}...")
    try:
        urllib.request.urlretrieve(URL, ZIP_NAME)
    except Exception as e:
        print(f"Download failed: {e}")
        return

    print("Extracting...")
    with zipfile.ZipFile(ZIP_NAME, 'r') as zip_ref:
        zip_ref.extractall(EXTRACT_DIR)

    # Find the bin folder
    bin_dir = None
    for root, dirs, files in os.walk(EXTRACT_DIR):
        if 'bin' in dirs:
            bin_dir = os.path.join(root, 'bin')
            break
    
    if bin_dir:
        if os.path.exists(TARGET_DIR):
            shutil.rmtree(TARGET_DIR)
        os.makedirs(TARGET_DIR)
        
        # Move bin contents to TARGET_DIR
        for f in os.listdir(bin_dir):
            shutil.move(os.path.join(bin_dir, f), os.path.join(TARGET_DIR, f))
        
        print(f"FFmpeg installed to {os.path.abspath(TARGET_DIR)}")
    else:
        print("Could not find bin directory in extracted files.")

    # Cleanup
    if os.path.exists(ZIP_NAME):
        os.remove(ZIP_NAME)
    if os.path.exists(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)

if __name__ == "__main__":
    install()
