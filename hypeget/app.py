"""Start the engine + local API and show the UI in a native window."""
from __future__ import annotations

import argparse
import json
import os
import webbrowser

from . import __version__, native_host, native_reg

from .config import Config
from .engine.manager import Manager
from .instance import SingleInstance, ask_running_app
from .server import ApiServer
from .tray import PystrayBackend, TrayController


UI_COMMANDS = {"show", "add"}     # what another start / the tray may ask the window to do


class WindowApi:
    """Exposed to JS as window.pywebview.api (custom title-bar buttons)."""

    def __init__(self, app_window: "AppWindow"):
        self._w = app_window
        self._maximized = False

    def minimize(self):
        self._w.window.minimize()

    def toggle_maximize(self):
        if self._maximized:
            self._w.window.restore()
        else:
            self._w.window.maximize()
        self._maximized = not self._maximized

    def close(self):
        """Title-bar X: hide to the tray when there is one, otherwise quit."""
        self._w.close()

    def quit(self):
        """Tasks > Exit: really quit."""
        self._w.quit()


class AppWindow:
    """The pywebview window plus tray behaviour: close hides, Exit quits."""

    def __init__(self, webview, url: str, manager: Manager, tray_ok, start_hidden: bool):
        self.manager = manager
        self.tray_ok = tray_ok           # callable: is the tray icon up?
        self.quitting = False
        self.api = WindowApi(self)
        self.window = webview.create_window(
            "HyperGet Downloader", url, js_api=self.api, width=1280, height=800,
            min_size=(960, 600), frameless=True, easy_drag=False, background_color="#FFFFFF",
            hidden=start_hidden)
        self.window.events.closing += self._on_closing
        manager.ui_show = self.show

    def _hide_instead(self) -> bool:
        return not self.quitting and self.tray_ok() and self.manager.config.settings.close_to_tray

    def _on_closing(self):
        # Alt+F4 / taskbar close: keep running in the tray. Returning False cancels the close.
        if self._hide_instead():
            self.window.hide()
            return False
        return True

    def close(self):
        if self._hide_instead():
            self.window.hide()
        else:
            self.quit()

    def show(self, command: str = "show"):
        command = command if command in UI_COMMANDS else "show"
        self.window.show()
        self.window.restore()
        try:                              # bring it in front of other windows
            self.window.on_top = True
            self.window.on_top = False
        except Exception:  # noqa: BLE001 - not supported everywhere
            pass
        if command != "show":
            self.window.evaluate_js(f"window.hgCommand && window.hgCommand({json.dumps(command)})")

    def quit(self):
        self.quitting = True
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
    ap.add_argument("--minimized", action="store_true", help="start in the notification area (Windows sign-in, browser)")
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

    instance = SingleInstance()
    if not instance.acquire():
        # HyperGet is already running: bring it forward instead of opening a second copy.
        if args.minimized or ask_running_app("show"):
            print("HyperGet is already running.")
        else:
            print("HyperGet is already running (no window to show).")
        return

    register_browsers()
    manager, server = start_backend(args.port)
    print(f"HyperGet running at {server.url}")
    tray = None
    try:
        if args.headless or args.browser:
            if args.browser:
                webbrowser.open(server.url)
                manager.ui_show = lambda command="show": webbrowser.open(server.url)
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

        holder: dict = {}
        ctl = TrayController(
            manager,
            show=lambda: holder["win"].show(),
            command=lambda cmd: holder["win"].show(cmd),
            quit_app=lambda: holder["win"].quit(),
            notify_enabled=lambda: manager.config.settings.notify_complete)
        tray = PystrayBackend(ctl)
        tray_up = tray.start()
        holder["win"] = AppWindow(webview, server.url, manager, tray_ok=lambda: tray_up,
                                  start_hidden=args.minimized and tray_up)
        webview.start()
    finally:
        if tray is not None:
            tray.stop()
        manager.ui_show = None
        clear_runtime(server.port)
        manager.shutdown()
        server.stop()
        instance.release()
