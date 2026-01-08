"""
Download Manager — Enhanced Prototype (main.py)
This is the main runnable GUI program. See README.md for usage.
"""
import sys
import os
import asyncio
import hashlib
import importlib.util
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
import aiosqlite
import aiohttp
from aiohttp import web, ClientTimeout, BasicAuth
from qasync import QEventLoop
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QProgressBar, QMessageBox,
    QSpinBox, QFileDialog, QHeaderView, QDialog, QFormLayout, QTextEdit,
    QDateTimeEdit, QCheckBox, QDialogButtonBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QClipboard
import pyqtgraph as pg
try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False


# Optional libtorrent
HAS_LIBTORRENT = False
try:
    import libtorrent as lt  # type: ignore
    HAS_LIBTORRENT = True
except Exception:
    HAS_LIBTORRENT = False

APP_DB = os.path.join(os.path.dirname(__file__), "downloads.db")
DEFAULT_SEGMENTS = 4
DEFAULT_CHUNK = 64 * 1024  # 64 KB
HTTP_SERVER_PORT = 8765

# Add local ffmpeg to PATH
ffmpeg_path = os.path.join(os.path.dirname(__file__), "ffmpeg")
if os.path.exists(ffmpeg_path):
    os.environ["PATH"] += os.pathsep + ffmpeg_path

@dataclass
class DownloadItem:
    id: int = 0
    url: str = ""
    filename: str = ""
    dest_folder: str = ""
    segments: int = DEFAULT_SEGMENTS
    checksum_sha256: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    cookies_raw: Optional[str] = None
    proxy: Optional[str] = None
    max_bandwidth: Optional[int] = None
    retries: int = 3
    quality: str = "Best"
    file_format: Optional[str] = None

    is_torrent: bool = False
    is_ytdlp: bool = False

    state: str = "queued"
    downloaded: int = 0
    total: Optional[int] = None
    progress: float = 0.0
    speed: float = 0.0
    error: Optional[str] = None

    _task: Optional[asyncio.Task] = None
    _pause_event: Optional[asyncio.Event] = None
    _cancel_event: Optional[asyncio.Event] = None
    _history_speeds: List[int] = field(default_factory=list)

# Global token bucket (simplified)
class GlobalTokenBucket:
    def __init__(self, loop, rate_bytes_per_sec: Optional[int] = None, capacity: int = 1_000_000):
        self._rate = rate_bytes_per_sec
        self._tokens = capacity
        self._capacity = max(capacity, 1)
        self._lock = asyncio.Lock()
        self._last = loop.time()
        self.loop = loop
        self._running = False
        self._refill_task = None

    def set_rate(self, rate: Optional[int]):
        self._rate = rate

    async def start(self):
        if self._running:
            return
        self._running = True
        self._refill_task = asyncio.create_task(self._refill_loop())

    async def _refill_loop(self):
        while self._running:
            await asyncio.sleep(0.1)
            async with self._lock:
                if not self._rate:
                    self._tokens = self._capacity
                else:
                    now = self.loop.time()
                    delta = now - self._last
                    add = delta * self._rate
                    if add >= 1:
                        self._tokens = min(self._capacity, self._tokens + add)
                        self._last = now

    async def acquire(self, nbytes: int):
        if not self._rate:
            return
        while True:
            async with self._lock:
                if self._tokens >= nbytes:
                    self._tokens -= nbytes
                    return
            await asyncio.sleep(0.02)

# Simple DB wrapper (aiosqlite)
class DB:
    def __init__(self, path=APP_DB):
        self.path = path
        self._conn = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT, filename TEXT, dest_folder TEXT, segments INTEGER,
                checksum_sha256 TEXT, scheduled_time TEXT, auth_username TEXT,
                auth_password TEXT, cookies_raw TEXT, proxy TEXT,
                max_bandwidth INTEGER, retries INTEGER, is_torrent INTEGER, is_ytdlp INTEGER,
                state TEXT, downloaded INTEGER, total INTEGER, quality TEXT, file_format TEXT
            )
        """)
        try:
            await self._conn.execute("ALTER TABLE downloads ADD COLUMN quality TEXT")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE downloads ADD COLUMN file_format TEXT")
        except Exception:
            pass
        await self._conn.commit()

    async def save_item(self, item: DownloadItem):
        if item.id and await self._exists(item.id):
            await self._conn.execute("""
                UPDATE downloads SET url=?, filename=?, dest_folder=?, segments=?, checksum_sha256=?,
                    scheduled_time=?, auth_username=?, auth_password=?, cookies_raw=?, proxy=?,
                    max_bandwidth=?, retries=?, is_torrent=?, is_ytdlp=?, state=?, downloaded=?, total=?, quality=?, file_format=? WHERE id=?
            """, (item.url, item.filename, item.dest_folder, item.segments, item.checksum_sha256,
                  item.scheduled_time.isoformat() if item.scheduled_time else None,
                  item.auth_username, item.auth_password, item.cookies_raw, item.proxy,
                  item.max_bandwidth, item.retries, int(item.is_torrent), int(item.is_ytdlp),
                  item.state, item.downloaded, item.total, item.quality, item.file_format, item.id))
            await self._conn.commit()
        else:
            cur = await self._conn.execute("""
                INSERT INTO downloads (url, filename, dest_folder, segments, checksum_sha256,
                    scheduled_time, auth_username, auth_password, cookies_raw, proxy,
                    max_bandwidth, retries, is_torrent, is_ytdlp, state, downloaded, total, quality, file_format)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (item.url, item.filename, item.dest_folder, item.segments, item.checksum_sha256,
                  item.scheduled_time.isoformat() if item.scheduled_time else None,
                  item.auth_username, item.auth_password, item.cookies_raw, item.proxy,
                  item.max_bandwidth, item.retries, int(item.is_torrent), int(item.is_ytdlp),
                  item.state, item.downloaded, item.total, item.quality, item.file_format))
            await self._conn.commit()
            item.id = cur.lastrowid

    async def _exists(self, id_):
        cur = await self._conn.execute("SELECT 1 FROM downloads WHERE id=?", (id_,))
        row = await cur.fetchone()
        return row is not None

    async def load_all(self):
        cur = await self._conn.execute("SELECT * FROM downloads ORDER BY id")
        rows = await cur.fetchall()
        items = []
        for r in rows:
            (id_, url, filename, dest_folder, segments, checksum_sha256,
             scheduled_time, auth_username, auth_password, cookies_raw,

             proxy, max_bandwidth, retries, is_torrent, is_ytdlp, state, downloaded, total, quality, file_format) = r
            item = DownloadItem(
                id=id_,
                url=url,
                filename=filename,
                dest_folder=dest_folder,
                segments=segments or DEFAULT_SEGMENTS,
                checksum_sha256=checksum_sha256,
                scheduled_time=datetime.fromisoformat(scheduled_time) if scheduled_time else None,
                auth_username=auth_username,
                auth_password=auth_password,
                cookies_raw=cookies_raw,
                proxy=proxy,
                max_bandwidth=max_bandwidth,
                retries=retries or 3,
                is_torrent=bool(is_torrent),
                is_ytdlp=bool(is_ytdlp) if is_ytdlp is not None else False,
                state=state or "queued",
                downloaded=downloaded or 0,
                total=total,
                quality=quality or "Best",
                file_format=file_format
            )
            item._pause_event = asyncio.Event()
            if item.state != "paused":
                item._pause_event.set()
            item._cancel_event = asyncio.Event()
            items.append(item)
        return items

# Download Manager core
class DownloadManager:
    def __init__(self, loop, ui_callback):
        self.loop = loop
        self.ui_update = ui_callback
        self.items: Dict[int, DownloadItem] = {}
        self.db = DB()
        self.session = None
        self.global_max_concurrency = 3
        self.active_count = 0
        self.global_bucket = GlobalTokenBucket(loop, rate_bytes_per_sec=None, capacity=1_000_000)
        if HAS_LIBTORRENT:
            self._init_libtorrent()

    async def init(self):
        await self.db.init()
        await self.global_bucket.start()
        await self.ensure_session()
        persisted = await self.db.load_all()
        for it in persisted:
            self.items[it.id] = it
        self.load_plugins()
        for it in list(self.items.values()):
            if it.state in ("queued", "running"):
                if it._pause_event and it.state != "paused":
                    it._pause_event.set()
        self.loop.create_task(self.maybe_start_pending())

    def load_plugins(self):
        plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
        if not os.path.isdir(plugins_dir):
            return
        for fname in os.listdir(plugins_dir):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(plugins_dir, fname)
            spec = importlib.util.spec_from_file_location(f"plugins.{fname[:-3]}", path)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)  # type: ignore
                if hasattr(mod, "register"):
                    try:
                        mod.register(self)
                    except Exception as e:
                        print("Plugin register error:", e)
            except Exception as e:
                print("Failed loading plugin", fname, e)

    async def ensure_session(self):
        if not self.session or self.session.closed:
            timeout = ClientTimeout(total=None)
            self.session = aiohttp.ClientSession(timeout=timeout)

    def add_item(self, item: DownloadItem):
        if item.id:
            self.items[item.id] = item
            self.loop.create_task(self.db.save_item(item))
        else:
            self.loop.create_task(self._save_and_register(item))

    async def _save_and_register(self, item):
        await self.db.init()
        await self.db.save_item(item)
        if item.id:
            self.items[item.id] = item
            item._pause_event = asyncio.Event()
            item._pause_event.set()
            item._cancel_event = asyncio.Event()
            self.ui_update(item.id)
            await self.maybe_start_pending()

    def remove_item(self, item_id):
        it = self.items.get(item_id)
        if not it:
            return
        if it._task and not it._task.done():
            it._cancel_event.set()
            it._task.cancel()
        async def _del():
            await self.db._conn.execute("DELETE FROM downloads WHERE id=?", (item_id,))
            await self._conn.commit()
        self.loop.create_task(_del())
        del self.items[item_id]
        self.ui_update(None)

    def pause_item(self, item_id):
        it = self.items.get(item_id)
        if not it:
            return
        it.state = "paused"
        if it._pause_event:
            it._pause_event.clear()
        self.loop.create_task(self.db.save_item(it))
        self.ui_update(item_id)

    def resume_item(self, item_id):
        it = self.items.get(item_id)
        if not it:
            return
        it.state = "queued"
        if it._pause_event:
            it._pause_event.set()
        self.loop.create_task(self.db.save_item(it))
        self.loop.create_task(self.maybe_start_pending())
        self.ui_update(item_id)

    def start_all(self):
        for it in self.items.values():
            if it.state in ("queued", "failed", "paused"):
                it.state = "queued"
                if it._pause_event:
                    it._pause_event.set()
                self.loop.create_task(self.db.save_item(it))
        self.loop.create_task(self.maybe_start_pending())

    async def maybe_start_pending(self):
        await self.ensure_session()
        for it in list(self.items.values()):
            if self.active_count >= self.global_max_concurrency:
                break
            if it.state == "queued":
                if it.scheduled_time and it.scheduled_time > datetime.now():
                    continue
                if self._is_youtube(it.url) or it.is_ytdlp:
                    it.is_ytdlp = True
                    self._launch_ytdlp(it)
                elif it.is_torrent:
                    if HAS_LIBTORRENT:
                        self._start_torrent(it)
                    else:
                        it.state = "failed"
                        it.error = "torrent support unavailable"
                        await self.db.save_item(it)
                        self.ui_update(it.id)
                else:
                    self._launch_http(it)

    def _launch_http(self, it: DownloadItem):
        if it._task and not it._task.done():
            return
        it.state = "running"
        it.error = None
        it._cancel_event = asyncio.Event()
        it._pause_event = asyncio.Event()
        it._pause_event.set()
        it._task = self.loop.create_task(self._download_with_retries(it))
        self.active_count += 1
        self.loop.create_task(self.db.save_item(it))
        self.ui_update(it.id)

    async def _download_with_retries(self, it: DownloadItem):
        attempt = 0
        backoff = 1
        while attempt <= it.retries:
            try:
                await self._download_http(it)
                it.state = "completed"
                it.progress = 100.0
                await self.db.save_item(it)
                self.ui_update(it.id)
                break
            except asyncio.CancelledError:
                it.state = "cancelled"
                it.error = "cancelled"
                await self.db.save_item(it)
                self.ui_update(it.id)
                break
            except Exception as e:
                attempt += 1
                it.error = f"attempt {attempt} failed: {e}"
                await self.db.save_item(it)
                self.ui_update(it.id)
                if attempt > it.retries:
                    it.state = "failed"
                    await self.db.save_item(it)
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        self.active_count = max(0, self.active_count - 1)
        await self.maybe_start_pending()

    async def _download_http(self, it: DownloadItem):
        await self.ensure_session()
        auth = None
        if it.auth_username and it.auth_password:
            auth = BasicAuth(it.auth_username, it.auth_password)
        dest = os.path.join(it.dest_folder, it.filename or os.path.basename(it.url.split("?",1)[0]) or f"dl_{it.id}")
        tmp_dir = os.path.join(it.dest_folder, f".dm_{it.id}")
        os.makedirs(tmp_dir, exist_ok=True)
        total = None
        accept_ranges = False
        try:
            async with self.session.head(it.url, auth=auth, proxy=it.proxy) as h:
                if h.status < 400:
                    total = int(h.headers.get("Content-Length") or 0) or None
                    accept_ranges = h.headers.get("Accept-Ranges", "none") != "none"
        except Exception:
            async with self.session.get(it.url, auth=auth, proxy=it.proxy) as g:
                g.raise_for_status()
                total = int(g.headers.get("Content-Length") or 0) or None
                accept_ranges = g.headers.get("Accept-Ranges", "none") != "none"
        it.total = total
        it.downloaded = 0
        self.ui_update(it.id)
        # segmented
        if total and accept_ranges and it.segments > 1:
            segs = []
            seg_size = total // it.segments
            for idx in range(it.segments):
                start = idx * seg_size
                end = (start + seg_size - 1) if idx < it.segments - 1 else total - 1
                segs.append((start, end, os.path.join(tmp_dir, f"seg-{idx}.part")))
            seg_tasks = []
            for s,e,p in segs:
                t = self.loop.create_task(self._download_range(it, s, e, p, auth))
                seg_tasks.append(t)
            await asyncio.gather(*seg_tasks)
            # merge
            with open(dest, "wb") as out_f:
                for _,_,p in segs:
                    with open(p, "rb") as sf:
                        while True:
                            chunk = sf.read(4 * 1024 * 1024)
                            if not chunk:
                                break
                            out_f.write(chunk)
            # cleanup
            try:
                for _,_,p in segs:
                    os.remove(p)
                os.rmdir(tmp_dir)
            except Exception:
                pass
        else:
            # single stream
            await self._download_range(it, 0, None, dest, auth, is_single=True)
        # checksum verify
        if it.checksum_sha256:
            h = hashlib.sha256()
            with open(dest, "rb") as f:
                for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest().lower() != it.checksum_sha256.lower():
                raise Exception("checksum mismatch")

    async def _download_range(self, it: DownloadItem, start, end, outpath, auth, is_single=False):
        existing = 0
        if os.path.exists(outpath):
            existing = os.path.getsize(outpath)
        range_start = start + existing if start is not None else None
        headers = {}
        if range_start is not None:
            if end is not None and range_start > end:
                return
            headers["Range"] = f"bytes={range_start}-{end if end is not None else ''}"
        req_kwargs = {}
        if auth:
            req_kwargs["auth"] = auth
        if it.proxy:
            req_kwargs["proxy"] = it.proxy
        async with self.session.get(it.url, headers=headers, **req_kwargs) as resp:
            resp.raise_for_status()
            mode = "ab" if existing else "wb"
            with open(outpath, mode) as f:
                while True:
                    await it._pause_event.wait()
                    if it._cancel_event.is_set():
                        raise asyncio.CancelledError()
                    chunk = await resp.content.read(DEFAULT_CHUNK)
                    if not chunk:
                        break
                    await self.global_bucket.acquire(len(chunk))
                    if it.max_bandwidth:
                        t_needed = len(chunk) / it.max_bandwidth
                        f.write(chunk)
                        it.downloaded += len(chunk)
                        await asyncio.sleep(t_needed * 0.95)
                    else:
                        f.write(chunk)
                        it.downloaded += len(chunk)
                    it._history_speeds.append(len(chunk))
                    if len(it._history_speeds) > 20:
                        it._history_speeds.pop(0)
                    it.speed = sum(it._history_speeds) / max(0.01, len(it._history_speeds))
                    if it.total:
                        # estimate progress
                        tmp_folder = os.path.dirname(outpath) if outpath.startswith(os.path.join(it.dest_folder, f".dm_{it.id}")) else None
                        current = 0
                        if tmp_folder and os.path.exists(tmp_folder):
                            for fn in os.listdir(tmp_folder):
                                current += os.path.getsize(os.path.join(tmp_folder, fn))
                        if os.path.exists(outpath):
                            current += os.path.getsize(outpath)
                        it.progress = min(100.0, (current / it.total) * 100.0)
                    else:
                        it.progress = 0.0
                    await self.db.save_item(it)
                    self.ui_update(it.id)

                    self.ui_update(it.id)

    def _is_youtube(self, url: str) -> bool:
        return "youtube.com" in url or "youtu.be" in url

    def _launch_ytdlp(self, it: DownloadItem):
        if not HAS_YTDLP:
            it.state = "failed"
            it.error = "yt-dlp not installed"
            self.loop.create_task(self.db.save_item(it))
            self.ui_update(it.id)
            return
        if it._task and not it._task.done():
            return
        it.state = "running"
        it.error = None
        it._cancel_event = asyncio.Event()
        it._pause_event = asyncio.Event()
        it._pause_event.set()
        # run blocking yt-dlp in thread
        it._task = self.loop.run_in_executor(None, self._run_ytdlp_blocking, it)
        self.active_count += 1
        self.loop.create_task(self.db.save_item(it))
        self.ui_update(it.id)

    def _run_ytdlp_blocking(self, it: DownloadItem):
        import time
        def progress_hook(d):
            # Check cancel
            if it._cancel_event and it._cancel_event.is_set():
                raise Exception("CancelledByUser")

            # Check pause - block immediately
            if it._pause_event:
                while not it._pause_event.is_set():
                     if it._cancel_event and it._cancel_event.is_set():
                         raise Exception("CancelledByUser")
                     time.sleep(0.5)

            if d['status'] == 'downloading':
                # Update stats
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                speed = d.get('speed')
                
                # Update in-memory object
                it.downloaded = downloaded or 0
                it.total = total or 0
                if total:
                    it.progress = (downloaded / total) * 100.0
                if speed:
                    it.speed = speed
            elif d['status'] == 'finished':
                it.progress = 100.0
                it.speed = 0.0
                filename = d.get('filename')
                if filename:
                    it.filename = os.path.basename(filename)


        # Select format
        format_sel = 'bestvideo+bestaudio/best'
        if it.quality == '1080p':
            format_sel = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
        elif it.quality == '720p':
            format_sel = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
        elif it.quality == 'Audio Only':
            format_sel = 'bestaudio/best'

        ydl_opts = {
            'outtmpl': os.path.join(it.dest_folder, '%(title)s.%(ext)s'),
            'format': format_sel,
            'progress_hooks': [progress_hook],
            'noplaylist': True,
            'no_color': True,
        }

        # Conversion logic
        if it.file_format:
            if it.quality == 'Audio Only':
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': it.file_format,
                    'preferredquality': '192',
                }]
            else:
                ydl_opts['merge_output_format'] = it.file_format
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([it.url])
            
            # success
            asyncio.run_coroutine_threadsafe(self._finalize_ytdlp(it, "completed"), self.loop)
        except Exception as e:
            if "CancelledError" in str(e): # hacky check if our hook raised it
                 asyncio.run_coroutine_threadsafe(self._finalize_ytdlp(it, "cancelled"), self.loop)
            else:
                 asyncio.run_coroutine_threadsafe(self._finalize_ytdlp(it, "failed", str(e)), self.loop)

    async def _finalize_ytdlp(self, it: DownloadItem, state, error=None):
        it.state = state
        if error:
            it.error = error
        await self.db.save_item(it)
        if state != "running":
            self.active_count = max(0, self.active_count - 1)
        self.ui_update(it.id)
        await self.maybe_start_pending()

    # libtorrent integration (simplified)
    def _init_libtorrent(self):
        self.torrent_session = lt.session()
        self.torrent_session.listen_on(6881, 6891)

    def _start_torrent(self, it: DownloadItem):
        if not HAS_LIBTORRENT:
            it.state = "failed"
            it.error = "libtorrent not available"
            self.loop.create_task(self.db.save_item(it))
            self.ui_update(it.id)
            return
        params = lt.add_torrent_params()
        if it.url.startswith("magnet:"):
            params = lt.parse_magnet_uri(it.url)
            params.save_path = it.dest_folder
        else:
            ti = lt.torrent_info(it.url)
            params.ti = ti
            params.save_path = it.dest_folder
        handle = self.torrent_session.add_torrent(params)
        it.state = "running"
        it._task = self.loop.create_task(self._monitor_torrent(it, handle))
        self.active_count += 1
        self.loop.create_task(self.db.save_item(it))
        self.ui_update(it.id)

    async def _monitor_torrent(self, it, handle):
        try:
            while not handle.is_seed():
                s = handle.status()
                it.progress = s.progress * 100.0
                it.downloaded = int(s.total_done)
                it.total = int(s.total_wanted)
                it.speed = s.download_rate
                await self.db.save_item(it)
                self.ui_update(it.id)
                await asyncio.sleep(1.0)
            it.state = "completed"
            await self.db.save_item(it)
            self.ui_update(it.id)
        except asyncio.CancelledError:
            it.state = "cancelled"
            await self.db.save_item(it)
            self.ui_update(it.id)
        finally:
            self.active_count = max(0, self.active_count - 1)
            await self.maybe_start_pending()

# UI
class AddDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Download")
        self.layout = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit()
        self.filename_edit = QLineEdit()
        self.dest_edit = QLineEdit(os.path.expanduser("~\\Downloads"))
        self.browse_btn = QPushButton("Browse")
        self.segs_spin = QSpinBox(); self.segs_spin.setRange(1, 32); self.segs_spin.setValue(DEFAULT_SEGMENTS)
        self.checksum_edit = QLineEdit()
        self.schedule_dt = QDateTimeEdit(datetime.now()); self.schedule_dt.setCalendarPopup(True)
        self.auth_user = QLineEdit()
        self.auth_pass = QLineEdit(); self.auth_pass.setEchoMode(QLineEdit.Password)
        self.cookies_text = QTextEdit()
        self.proxy_edit = QLineEdit()
        self.bandwidth_spin = QSpinBox(); self.bandwidth_spin.setRange(0, 10_000_000); self.bandwidth_spin.setValue(0)
        self.retries_spin = QSpinBox(); self.retries_spin.setRange(0, 20); self.retries_spin.setValue(3)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Select Quality...", "Best", "1080p", "720p", "Audio Only"])
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Select Format..."])
        self.format_combo.setEnabled(False)

        self.quality_combo.currentTextChanged.connect(self.on_quality_changed)
        
        self.is_torrent_cb = QCheckBox("Is torrent / magnet")
        form.addRow("URL:", self.url_edit)
        form.addRow("Filename (optional):", self.filename_edit)
        h = QHBoxLayout(); h.addWidget(self.dest_edit); h.addWidget(self.browse_btn)
        form.addRow("Destination:", h)
        form.addRow("Segments:", self.segs_spin)
        form.addRow("Per-download bandwidth (KB/s, 0=none):", self.bandwidth_spin)
        form.addRow("Retries:", self.retries_spin)

        form.addRow("Quality (Youtube):", self.quality_combo)
        form.addRow("Format (Youtube):", self.format_combo)
        form.addRow("Checksum (SHA256):", self.checksum_edit)
        form.addRow("Schedule:", self.schedule_dt)
        form.addRow("Auth username:", self.auth_user); form.addRow("Auth password:", self.auth_pass)
        form.addRow("Cookies (JSON or name=value lines):", self.cookies_text)
        form.addRow("Proxy (http://proxy:port):", self.proxy_edit)
        form.addRow("", self.is_torrent_cb)
        self.layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.layout.addWidget(self.buttons)
        self.browse_btn.clicked.connect(self.on_browse)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
        # Initial validation check
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True) 

    def on_quality_changed(self, text):
        self.format_combo.clear()
        if text == "Select Quality...":
            self.format_combo.addItem("Select Format...")
            self.format_combo.setEnabled(False)
        elif text == "Audio Only":
            self.format_combo.setEnabled(True)
            self.format_combo.addItems(["mp3", "m4a", "wav"])
        else: # Video
            self.format_combo.setEnabled(True)
            self.format_combo.addItems(["mp4", "mkv", "webm"])

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select destination folder", self.dest_edit.text())
        if folder:
            self.dest_edit.setText(folder)

    def accept(self):
        # Validate inputs
        if self.url_edit.text().strip() and ("youtube" in self.url_edit.text().strip() or "youtu.be" in self.url_edit.text().strip()):
             if self.quality_combo.currentText() == "Select Quality...":
                 QMessageBox.warning(self, "Invalid Selection", "Please select a Quality.")
                 return
             if self.format_combo.currentText() == "Select Format..." or not self.format_combo.currentText():
                 QMessageBox.warning(self, "Invalid Selection", "Please select a Format.")
                 return
        super().accept()

    def get_data(self):
        if self.exec() != QDialog.Accepted:
            return None
        url = self.url_edit.text().strip()
        if not url:
            return None
        filename = self.filename_edit.text().strip() or os.path.basename(url.split("?",1)[0]) or f"dl_{int(datetime.now().timestamp())}"
        scheduled = self.schedule_dt.dateTime().toPython()
        bw = self.bandwidth_spin.value()
        
        quality = self.quality_combo.currentText()
        if quality == "Select Quality...": quality = "Best" # Fallback if validation bypassed (shouldn't happen)
        file_fmt = self.format_combo.currentText()
        if not file_fmt or file_fmt == "Select Format...": file_fmt = None

        return {
            "url": url,
            "filename": filename,
            "dest_folder": self.dest_edit.text(),
            "segments": self.segs_spin.value(),
            "checksum_sha256": self.checksum_edit.text().strip() or None,
            "scheduled_time": scheduled if scheduled and scheduled > datetime(1970,1,1) else None,
            "auth_username": self.auth_user.text().strip() or None,
            "auth_password": self.auth_pass.text() or None,
            "cookies_raw": self.cookies_text.toPlainText().strip() or None,
            "proxy": self.proxy_edit.text().strip() or None,
            "max_bandwidth": bw * 1024 if bw else None,
            "retries": self.retries_spin.value(),

            "quality": quality,
            "file_format": file_fmt,
            "is_torrent": self.is_torrent_cb.isChecked()
        }

class DetailDialog(QDialog):
    def __init__(self, item: DownloadItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Details — {item.filename}")
        self.resize(600, 400)
        self.layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget()
        self.layout.addWidget(self.plot_widget)
        self.plot = self.plot_widget.plot(pen='y')
        self.item = item
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(800)

    def update_plot(self):
        if not self.item:
            return
        data = list(self.item._history_speeds[-60:])
        y = [v/1024.0 for v in data]
        self.plot.setData(y)

class MainWindow(QWidget):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.setWindowTitle("Download Manager — Enhanced Prototype")
        self.resize(1100, 600)
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        self.add_btn = QPushButton("Add Download")
        self.start_all_btn = QPushButton("Start All")
        self.pause_all_btn = QPushButton("Pause All")
        self.settings_btn = QPushButton("Settings")
        h.addWidget(self.add_btn); h.addWidget(self.start_all_btn); h.addWidget(self.pause_all_btn); h.addWidget(self.settings_btn)
        v.addLayout(h)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["ID", "Name/URL", "Progress", "Speed", "State", "Total", "Scheduled", "Errors", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents)
        v.addWidget(self.table)
        sh = QHBoxLayout()
        sh.addWidget(QLabel("Global max concurrency:"))
        self.max_concurrency_spin = QSpinBox(); self.max_concurrency_spin.setRange(1, 20); self.max_concurrency_spin.setValue(3)
        sh.addWidget(self.max_concurrency_spin)
        sh.addWidget(QLabel("Global bandwidth (KB/s, 0=none):"))
        self.global_bw_spin = QSpinBox(); self.global_bw_spin.setRange(0, 10_000_000); self.global_bw_spin.setValue(0)
        sh.addWidget(self.global_bw_spin)
        v.addLayout(sh)
        self.setLayout(v)
        self.manager = DownloadManager(self.loop, self.ui_update)
        self.add_btn.clicked.connect(self.on_add)
        self.start_all_btn.clicked.connect(lambda: self.manager.start_all())
        self.pause_all_btn.clicked.connect(self.on_pause_all)
        self.settings_btn.clicked.connect(self.on_settings)
        self.table.cellDoubleClicked.connect(self.on_double_click)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_ui)
        self.timer.start(700)
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        self.loop.create_task(self.manager.init())
        self.loop.create_task(self.start_http_server())

    async def start_http_server(self):
        app = web.Application()
        async def add_handler(request):
            try:
                j = await request.json()
            except Exception:
                j = await request.post()
            url = j.get("url") if isinstance(j, dict) else None
            if not url:
                return web.json_response({"error": "no url"}, status=400)
            filename = os.path.basename(url.split("?",1)[0]) or f"dl_{int(datetime.now().timestamp())}"
            item = DownloadItem(
                url=url, filename=filename, dest_folder=os.path.expanduser("~\\Downloads"),
                segments=DEFAULT_SEGMENTS, retries=3,
                is_torrent=(url.startswith("magnet:") or url.endswith(".torrent"))
            )
            self.manager.add_item(item)
            return web.json_response({"ok": True, "id": item.id})
        app.router.add_post("/add", add_handler)
        app.router.add_get("/extension", lambda req: web.Response(text="<html><body><h3>Install extension from the chrome-extension folder</h3></body></html>", content_type="text/html"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", HTTP_SERVER_PORT)
        await site.start()
        print(f"HTTP extension endpoint available on http://127.0.0.1:{HTTP_SERVER_PORT}/add")

    def on_add(self):
        dlg = AddDialog(self)
        data = dlg.get_data()
        if not data:
            return
        item = DownloadItem(
            url=data["url"],
            filename=data["filename"],
            dest_folder=data["dest_folder"],
            segments=data["segments"],
            checksum_sha256=data["checksum_sha256"],
            scheduled_time=data["scheduled_time"],
            auth_username=data["auth_username"],
            auth_password=data["auth_password"],
            cookies_raw=data["cookies_raw"],
            proxy=data["proxy"],
            max_bandwidth=data["max_bandwidth"],
            retries=data["retries"],
            quality=data["quality"],
            file_format=data["file_format"],
            is_torrent=data["is_torrent"]
        )
        self.manager.add_item(item)

    def on_pause_all(self):
        for it in self.manager.items.values():
            self.manager.pause_item(it.id)

    def on_settings(self):
        self.manager.global_max_concurrency = self.max_concurrency_spin.value()
        gbw = self.global_bw_spin.value()
        self.manager.global_bucket.set_rate(None if gbw == 0 else gbw * 1024)
        QMessageBox.information(self, "Settings", "Settings applied.")

    def on_double_click(self, row, col):
        itemid_item = self.table.item(row, 0)
        if not itemid_item:
            return
        iid = int(itemid_item.text())
        it = self.manager.items.get(iid)
        if not it:
            return
        dlg = DetailDialog(it, self)
        dlg.exec()

    def on_clipboard_change(self):
        txt = self.clipboard.text()
        if not txt:
            return
        if txt.startswith("http://") or txt.startswith("https://") or txt.startswith("magnet:") or txt.endswith(".torrent"):
            if QMessageBox.question(self, "URL detected", f"Add URL?\n{txt}") == QMessageBox.Yes:
                item = DownloadItem(
                    url=txt,
                    filename=os.path.basename(txt.split("?",1)[0]) or f"dl_{int(datetime.now().timestamp())}",
                    dest_folder=os.path.expanduser("~\\Downloads"),
                    segments=DEFAULT_SEGMENTS
                )
                self.manager.add_item(item)

    def ui_update(self, item_id: Optional[int]):
        self.refresh_ui()

    def refresh_ui(self):
        items = list(self.manager.items.values())
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            # ID
            item_id = self.table.item(r, 0)
            if not item_id:
                item_id = QTableWidgetItem(str(it.id))
                self.table.setItem(r, 0, item_id)
            else:
                if item_id.text() != str(it.id):
                    item_id.setText(str(it.id))

            # Name/URL
            item_name = self.table.item(r, 1)
            txt = f"{it.filename}\n{it.url}"
            if not item_name:
                self.table.setItem(r, 1, QTableWidgetItem(txt))
            else:
                if item_name.text() != txt:
                    item_name.setText(txt)

            # Progress
            prog = self.table.cellWidget(r, 2)
            if not prog:
                prog = QProgressBar()
                self.table.setCellWidget(r, 2, prog)
            prog.setValue(int(it.progress or 0))

            # Speed
            speed_str = f"{it.speed/1024:.1f} KB/s" if it.speed else ""
            item_speed = self.table.item(r, 3)
            if not item_speed:
                self.table.setItem(r, 3, QTableWidgetItem(speed_str))
            else:
                if item_speed.text() != speed_str:
                    item_speed.setText(speed_str)

            # State
            item_state = self.table.item(r, 4)
            if not item_state:
                self.table.setItem(r, 4, QTableWidgetItem(it.state))
            else:
                if item_state.text() != it.state:
                   item_state.setText(it.state)

            # Total
            total_str = str(it.total) if it.total else ""
            item_total = self.table.item(r, 5)
            if not item_total:
                self.table.setItem(r, 5, QTableWidgetItem(total_str))
            else:
                if item_total.text() != total_str:
                    item_total.setText(total_str)

            # Scheduled
            st = it.scheduled_time.strftime("%Y-%m-%d %H:%M:%S") if it.scheduled_time else ""
            item_sched = self.table.item(r, 6)
            if not item_sched:
                self.table.setItem(r, 6, QTableWidgetItem(st))
            else:
                 if item_sched.text() != st:
                     item_sched.setText(st)

            # Errors
            err_str = it.error or ""
            item_err = self.table.item(r, 7)
            if not item_err:
                self.table.setItem(r, 7, QTableWidgetItem(err_str))
            else:
                if item_err.text() != err_str:
                    item_err.setText(err_str)

            # Actions
            if not self.table.cellWidget(r, 8):
                aw = QWidget(); ah = QHBoxLayout(); ah.setContentsMargins(0,0,0,0)
                start_btn = QPushButton("Start"); pause_btn = QPushButton("Pause"); cancel_btn = QPushButton("Cancel")
                ah.addWidget(start_btn); ah.addWidget(pause_btn); ah.addWidget(cancel_btn)
                aw.setLayout(ah)
                start_btn.clicked.connect(lambda _, iid=it.id: self.manager.resume_item(iid))
                pause_btn.clicked.connect(lambda _, iid=it.id: self.manager.pause_item(iid))
                cancel_btn.clicked.connect(lambda _, iid=it.id: self._cancel(iid))
                self.table.setCellWidget(r, 8, aw)

    def _cancel(self, iid):
        it = self.manager.items.get(iid)
        if not it:
            return
        if it._task and not it._task.done():
            it._cancel_event.set()
            it._task.cancel()
            it.state = "cancelled"
            self.loop.create_task(self.manager.db.save_item(it))
            self.ui_update(iid)
        else:
            self.manager.remove_item(iid)

def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    w = MainWindow(loop)
    w.show()
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
