from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass

from werkzeug.serving import make_server

from app import app


APP_NAME = "美股低估筛选与 BTC 周期仪表盘"
HOST = "127.0.0.1"
DEFAULT_PORT = 5000


def find_free_port(start: int = DEFAULT_PORT, limit: int = 20) -> int:
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("没有找到可用端口，请关闭占用 5000 附近端口的程序后重试。")


@dataclass
class LocalServer:
    port: int

    def __post_init__(self) -> None:
        self.url = f"http://{HOST}:{self.port}"
        self._server = make_server(HOST, self.port, app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._server.shutdown()
        self._thread.join(timeout=3)
        self._running = False


class DesktopApp:
    def __init__(self) -> None:
        self.server = LocalServer(find_free_port())

    def run(self) -> None:
        import webview

        self.server.start()
        try:
            webview.create_window(
                APP_NAME,
                self.server.url,
                width=1440,
                height=960,
                min_size=(1100, 720),
                text_select=True,
            )
            webview.start(private_mode=False)
        finally:
            self.server.stop()


def smoke_test() -> int:
    server = LocalServer(find_free_port(5100))
    server.start()
    try:
        with urllib.request.urlopen(f"{server.url}/api/health", timeout=10) as response:
            return 0 if response.status == 200 else 1
    finally:
        server.stop()


def webview_smoke_test() -> int:
    import webview

    server = LocalServer(find_free_port(5200))
    server.start()
    window = webview.create_window(APP_NAME, server.url, hidden=True)

    def close_window() -> None:
        time.sleep(1)
        window.destroy()

    try:
        webview.start(close_window, private_mode=False)
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(smoke_test())
    if "--webview-smoke-test" in sys.argv:
        raise SystemExit(webview_smoke_test())

    DesktopApp().run()
