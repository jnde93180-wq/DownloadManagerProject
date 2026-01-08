"""
Simple test HTTP server that streams a large pseudo-file for testing downloads.

Run:
    python test_server.py

Endpoints:
- GET /large -> streams ~200MB of deterministic bytes (for testing segmented downloads)
"""
import asyncio
from aiohttp import web

CHUNK = b"0123456789ABCDEF" * 4096  # ~64 KB per chunk
TOTAL_BYTES = 200 * 1024 * 1024  # ~200 MB

async def large_handler(request):
    async def stream(resp):
        sent = 0
        while sent < TOTAL_BYTES:
            await resp.write(CHUNK)
            sent += len(CHUNK)
            # Slight delay to mimic network latency
            await asyncio.sleep(0.001)
        await resp.write_eof()

    headers = {
        "Content-Length": str(TOTAL_BYTES),
        "Accept-Ranges": "bytes",
        "Content-Type": "application/octet-stream",
    }
    return web.Response(body=stream, headers=headers)

async def init_app():
    app = web.Application()
    app.router.add_get("/large", large_handler)
    return app

def main():
    app = web.Application()
    app.router.add_get("/large", large_handler)
    web.run_app(app, host="127.0.0.1", port=8080)

if __name__ == "__main__":
    main()
