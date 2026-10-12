"""Local web app: FastAPI backend + browser interface.

The closed loop and the trigger scheduler run in Python (a background thread calls
``Session.tick`` every 20 ms); the browser only draws state frames and sends commands
over a WebSocket. Timing therefore never depends on the browser.
"""

# No `from __future__ import annotations` here: FastAPI must see the real WebSocket class
# in the endpoint signature (it is imported lazily, inside create_app).
import asyncio
import threading
import time
import webbrowser
from pathlib import Path

from .. import __version__
from ..session import TICK_S, Session

STATIC = Path(__file__).parent / "static"
FRAME_S = 0.05


def create_app(session: Session, tick: bool = True):
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles

    stop = threading.Event()

    def loop():
        while not stop.is_set():
            session.tick()
            time.sleep(TICK_S)

    async def lifespan(app):
        thread = threading.Thread(target=loop, daemon=True) if tick else None
        if thread:
            thread.start()
        yield
        stop.set()
        session.close()

    app = FastAPI(title="NeuroBack", version=__version__, lifespan=lifespan)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({"type": "hello", "version": __version__, "live": True, **Session.hello()})

        async def sender():
            while True:
                state = await asyncio.to_thread(session.snapshot)
                await websocket.send_json({"type": "state", **state})
                await asyncio.sleep(FRAME_S)

        task = asyncio.create_task(sender())
        try:
            while True:
                msg = await websocket.receive_json()
                reply = await asyncio.to_thread(session.command, msg)
                await websocket.send_json({"type": "reply", "id": msg.get("id"), **reply})
        except WebSocketDisconnect:
            pass
        finally:
            task.cancel()

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


def serve(session: Session, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"NeuroBack running at {url}  (Ctrl+C to quit)")
    uvicorn.run(create_app(session), host=host, port=port, log_level="warning")
