from __future__ import annotations

import socket
import threading

from werkzeug.serving import make_server

from app import app


HOST = "127.0.0.1"
DEFAULT_PORT = 5000
_server = None
_thread = None
_url = None


def _find_free_port(start: int = DEFAULT_PORT, limit: int = 20) -> int:
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("没有找到可用端口")


def start_server() -> str:
    global _server, _thread, _url
    if _server is not None and _url is not None:
        return _url

    port = _find_free_port()
    _server = make_server(HOST, port, app)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    _url = f"http://{HOST}:{port}"
    return _url


def stop_server() -> None:
    global _server, _thread, _url
    if _server is None:
        return
    _server.shutdown()
    if _thread is not None:
        _thread.join(timeout=3)
    _server = None
    _thread = None
    _url = None
