"""Dashboard server launcher: uvicorn on 127.0.0.1 + browser open."""

from __future__ import annotations

import threading
import webbrowser

import uvicorn

from .api import create_app


def serve(port: int = 8899, open_browser: bool = True) -> None:
    app = create_app()

    if open_browser:
        # Give uvicorn a moment to bind before the browser hits it.
        threading.Timer(1.0, webbrowser.open, args=(f"http://127.0.0.1:{port}",)).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
