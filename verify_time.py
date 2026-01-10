
import asyncio
import os
import shutil
import time
from datetime import datetime
from main import DownloadManager, DownloadItem

async def main():
    loop = asyncio.get_event_loop()
    manager = DownloadManager(loop, lambda iid: None)
    await manager.init()

    # Create temp dir
    td = os.path.join(os.path.dirname(__file__), "verify_temp")
    if os.path.exists(td):
        shutil.rmtree(td)
    os.makedirs(td)

    item = DownloadItem(
        url="http://127.0.0.1:8081/small",
        filename="small.txt",
        dest_folder=td,
        segments=1
    )
    
    manager.add_item(item)
    
    with open("verify_result.txt", "w") as f:
        f.write("Waiting for download...\n")
    
    print("Waiting for download...")
    while True:
        await asyncio.sleep(0.5)
        it = manager.items.get(item.id)
        if not it:
            continue
        if it.state == "completed":
            print("Download completed.")
            print(f"DEBUG: start_time={it.start_time} end_time={it.end_time}")
            if it.start_time is not None and it.end_time is not None:
                duration = it.end_time - it.start_time
                print(f"Duration: {duration:.4f}s")
                if duration >= 0:
                    print("PASS: Duration is valid.")
                else:
                    print("FAIL: Duration is negative.")
            else:
                print(f"FAIL: start_time={it.start_time}, end_time={it.end_time}")
            break
        elif it.state == "failed":
            with open("verify_result.txt", "a") as f:
                f.write(f"FAIL: Download failed with error: {it.error}\n")
            break
        elif it.state == "cancelled":
            with open("verify_result.txt", "a") as f:
                f.write("FAIL: Download cancelled\n")
            break

    await manager.session.close()
    
if __name__ == "__main__":
    asyncio.run(main())
