"""
Headless smoke test for segmented download behavior.
Starts a DownloadManager (no GUI), adds an item for http://127.0.0.1:8080/large and waits
for completion, printing progress to stdout.

Usage:
    python run_smoke.py

Note: Make sure `test_server.py` is running (it serves /large on 127.0.0.1:8080).
"""
import asyncio
import tempfile
import shutil
import os
from datetime import datetime

from main import DownloadManager, DownloadItem


async def main():
    loop = asyncio.get_event_loop()
    manager = DownloadManager(loop, lambda iid: None)
    await manager.init()

    base = os.path.join(os.path.dirname(__file__), "smoke_temp")
    os.makedirs(base, exist_ok=True)
    td = os.path.join(base, f"run_{int(datetime.now().timestamp())}")
    os.makedirs(td, exist_ok=True)
    print("Using temp folder:", td)

    item = DownloadItem(
        url="http://127.0.0.1:8080/large",
        filename="large_test.bin",
        dest_folder=td,
        segments=4,
        retries=1
    )

    # register simple hook for progress
    def on_progress(it):
        print(f"Progress: id={it.id} state={it.state} progress={it.progress:.2f}% downloaded={it.downloaded}")

    manager.register_hook('on_item_progress', on_progress)
    manager.add_item(item)

    # wait until completed/failed/cancelled or timeout
    start = datetime.now()
    timeout = 120  # seconds
    while True:
        await asyncio.sleep(1)
        it = None
        if item.id:
            it = manager.items.get(item.id)
        if it:
            print(f"[STATUS] id={it.id} state={it.state} progress={it.progress:.2f}%")
            if it.state in ("completed", "failed", "cancelled"):
                # print error if any
                if it.error:
                    print("Error:", it.error)
                break
        if (datetime.now() - start).total_seconds() > timeout:
            print("Timeout waiting for download to finish")
            break

    # cleanup
    if os.path.exists(td):
        print("Contents of temp folder:", os.listdir(td))
    else:
        print("Temp folder missing")

    await manager.session.close()
    try:
        shutil.rmtree(td)
    except Exception:
        pass

if __name__ == '__main__':
    asyncio.run(main())
