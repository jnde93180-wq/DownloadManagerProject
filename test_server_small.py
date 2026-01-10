
import asyncio
from aiohttp import web

async def small_handler(request):
    return web.Response(text="Hello World " * 100)

async def init_app():
    app = web.Application()
    app.router.add_get("/small", small_handler)
    return app

def main():
    app = web.Application()
    app.router.add_get("/small", small_handler)
    web.run_app(app, host="127.0.0.1", port=8081)

if __name__ == "__main__":
    main()
