"""Start the engine + local API and show the UI in a native window."""
from __future__ import annotations

import argparse
import json
import os
import webbrowser

from . import __version__, native_host, native_reg

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
        # Port busy: take any free port. The browser helper finds us through
        # runtime.json, so the exact port doesn't matter.
        server = ApiServer(manager, 0).start()
    write_runtime(server.port)
    return manager, server


def write_runtime(port: int) -> None:
    """Tell the browser helper (native_host) where this running app listens."""
    path = native_host.runtime_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"port": port, "pid": os.getpid(), "version": __version__}, f)
    os.replace(tmp, path)


def clear_runtime(port: int) -> None:
    path = native_host.runtime_path()
    try:
        with open(path, encoding="utf-8") as f:
            if json.load(f).get("port") != port:
                return          # another instance owns it now
        os.remove(path)
    except (OSError, ValueError):
        pass


def register_browsers(quiet: bool = True) -> None:
    try:
        places = native_reg.register()
        if not quiet:
            print("Registered browser integration:", *places, sep="\n  ")
    except Exception as e:  # noqa: BLE001 - never block the app on this
        if not quiet:
            print("Could not register browser integration:", e)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="hypeget", description="HyperGet Downloader")
    ap.add_argument("--browser", action="store_true", help="open the UI in your web browser instead of a window")
    ap.add_argument("--headless", action="store_true", help="run the engine + API only (no UI)")
    ap.add_argument("--port", type=int, default=None, help="API port (default from settings: 52817)")
    ap.add_argument("--register", action="store_true", help="register the browser integration and exit")
    ap.add_argument("--unregister", action="store_true", help="remove the browser integration and exit")
    args = ap.parse_args(argv)

    if args.register:
        register_browsers(quiet=False)
        return
    if args.unregister:
        native_reg.unregister()
        return
    if args.port is None and native_host.app_port():
        # Already running (e.g. started by the browser helper): don't open a second copy.
        print("HyperGet is already running.")
        return

    register_browsers()
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
        clear_runtime(server.port)
        manager.shutdown()
        server.stop()
