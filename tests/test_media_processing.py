import unittest
import asyncio
import os
from unittest.mock import MagicMock, patch, AsyncMock
from main import DownloadManager, DownloadItem

class TestMediaProcessing(unittest.IsolatedAsyncioTestCase):
    async def test_post_process_media_audio(self):
        # Setup
        loop = asyncio.get_running_loop()
        manager = DownloadManager(loop, lambda x: None)
        
        item = DownloadItem(
            id=1,
            url="http://example.com/audio.wav",
            filename="audio.wav",
            dest_folder=".",
            quality="High (320k)",
            file_format="mp3"
        )
        
        # Mock subprocess
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc
            
            # Create dummy file
            with open("audio.wav", "wb") as f:
                f.write(b"dummy audio content")
                
            # Mock os.rename and os.remove to avoid actual file system changes (except creation above)
            with patch("os.remove") as mock_remove, \
                 patch("os.rename") as mock_rename, \
                 patch("os.path.exists", return_value=True) as mock_exists, \
                 patch("os.path.getsize", return_value=1024) as mock_getsize:
                 
                await manager._post_process_media(item)
                
                # Verify ffmpeg called with correct args
                args = mock_exec.call_args[0]
                self.assertIn("ffmpeg", args)
                self.assertIn("-b:a", args)
                self.assertIn("320k", args)
                self.assertTrue(args[-1].endswith("_processed.mp3"))
                
                # Verify file operations
                self.assertTrue(mock_rename.called)
                self.assertEqual(item.filename, "audio.mp3")

        # Cleanup
        if os.path.exists("audio.wav"):
            os.remove("audio.wav")

    async def test_post_process_media_image(self):
        # Setup
        loop = asyncio.get_running_loop()
        manager = DownloadManager(loop, lambda x: None)
        
        item = DownloadItem(
            id=2,
            url="http://example.com/image.png",
            filename="image.png",
            dest_folder=".",
            quality="Medium",
            file_format="jpg"
        )
        
        # Mock subprocess
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc
            
            # Create dummy file
            with open("image.png", "wb") as f:
                f.write(b"dummy image content")
                
            # Mock os.remove/rename
            with patch("os.remove") as mock_remove, \
                 patch("os.rename") as mock_rename, \
                 patch("os.path.exists", return_value=True) as mock_exists, \
                 patch("os.path.getsize", return_value=1024) as mock_getsize:
                 
                await manager._post_process_media(item)
                
                # Verify ffmpeg called
                args = mock_exec.call_args[0]
                self.assertIn("ffmpeg", args)
                self.assertIn("-q:v", args)
                self.assertIn("10", args) # Medium -> 10
                self.assertTrue(args[-1].endswith("_processed.jpg"))
                
                self.assertTrue(mock_rename.called)
                self.assertEqual(item.filename, "image.jpg")

        # Cleanup
        if os.path.exists("image.png"):
            os.remove("image.png")
