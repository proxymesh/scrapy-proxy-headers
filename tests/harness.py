"""Local CONNECT proxy and HTTPS target for compatibility tests."""

from __future__ import annotations

import asyncio
import json
import socket
import ssl
import subprocess
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def write_self_signed_cert(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        f"openssl req -x509 -newkey rsa:2048 -keyout {key} -out {cert} "
        "-days 1 -nodes -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1".split(),
        check=True,
        capture_output=True,
    )
    return cert, key


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def _handle(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, log_path: Path
) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, ConnectionError):
        writer.close()
        return
    lines = head.decode("iso-8859-1", "replace").split("\r\n")
    method, target, *_rest = (*lines[0].split(" "), "", "")
    pairs = []
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        pairs.append([key.strip(), value.strip()])
    event = {"method": method, "target": target, "headers": pairs}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    country = next(
        (value for key, value in pairs if key.lower() == "x-proxymesh-country"), ""
    )
    host, port_text = target.rsplit(":", 1)
    remote_reader, remote_writer = await asyncio.open_connection(host, int(port_text))
    writer.write(
        b"HTTP/1.1 200 Connection established\r\n"
        b"X-Test-Proxy: 1\r\n"
        b"X-Echo-Country: " + country.encode() + b"\r\n\r\n"
    )
    await writer.drain()
    await asyncio.gather(_pipe(reader, remote_writer), _pipe(remote_reader, writer))


def start_connect_proxy(log_path: Path) -> tuple[int, Callable[[], None]]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    loop = asyncio.new_event_loop()

    async def client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await _handle(reader, writer, log_path)

    async def serve() -> None:
        server = await asyncio.start_server(client, sock=sock)
        try:
            await asyncio.get_running_loop().create_future()
        finally:
            server.close()
            await server.wait_closed()

    def run() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(serve())
        except asyncio.CancelledError:
            pass

    def stop() -> None:
        def _cancel() -> None:
            for task in asyncio.all_tasks(loop):
                task.cancel()

        if loop.is_running():
            loop.call_soon_threadsafe(_cancel)
        thread.join(timeout=5)
        sock.close()
        if not loop.is_closed():
            loop.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return sock.getsockname()[1], stop


class _TargetHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = json.dumps({"headers": dict(self.headers.items())}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:
        return


def start_https_target(cert: Path, key: Path) -> tuple[int, Callable[[], None]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TargetHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(
        target=server.serve_forever, name="https-target", daemon=True
    ).start()
    return server.server_address[1], lambda: (server.shutdown(), server.server_close())


def read_proxy_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
