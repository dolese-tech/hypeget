"""Start the engine + local API and show the UI in a native window."""
from __future__ import annotations

import argparse
import webbrowser

from .config import Config
from .engine.manager import Manager
from .server import ApiServer


class WindowApi:
    """Exposed to JS as window.pywebview.api (custom title-bar buttons)."""

    def __init__(self):
        self.window = None
        self._maximized = False

    def minimize(self):
        self.window.minimize()

    def toggle_maximize(self):
        if self._maximized:
            self.window.restore()
        else:
            self.window.maximize()
        self._maximized = not self._maximized

    def close(self):
        self.window.destroy()


def start_backend(port: int | None = None) -> tuple[Manager, ApiServer]:
    config = Config()
    manager = Manager(config)
    want = config.settings.api_port if port is None else port
    try:
        server = ApiServer(manager, want).start()
    except OSError:
        # Port busy (another copy running?) - fall back to any free port.
        # The browser extension won't find this instance, so say so.
        server = ApiServer(manager, 0).start()
        print(f"Port {want} busy; using {server.port}. The browser extension expects {want}.")
    return manager, server


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="hypeget", description="HyperGet Downloader")
    ap.add_argument("--browser", action="store_true", help="open the UI in your web browser instead of a window")
    ap.add_argument("--headless", action="store_true", help="run the engine + API only (no UI)")
    ap.add_argument("--port", type=int, default=None, help="API port (default from settings: 52817)")
    args = ap.parse_args(argv)

    manager, server = start_backend(args.port)
    print(f"HyperGet running at {server.url}")
    try:
        if args.headless or args.browser:
            if args.browser:
                webbrowser.open(server.url)
            try:
                server.thread.join()
            except KeyboardInterrupt:
                pass
            return
        try:
            import webview  # pywebview
        except ImportError:
            print("pywebview not installed; opening in your browser instead.")
            webbrowser.open(server.url)
            server.thread.join()
            return
        api = WindowApi()
        api.window = webview.create_window(
            "HyperGet Downloader", server.url, js_api=api, width=1280, height=800,
            min_size=(960, 600), frameless=True, easy_drag=False, background_color="#FFFFFF")
        webview.start()
    finally:
        manager.shutdown()
        server.stop()
