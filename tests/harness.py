"""Local CONNECT proxy and HTTPS target for compatibility tests."""

from __future__ import annotations

import asyncio
import json
import ssl
import subprocess
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def write_self_signed_cert(directory: Path) -> tuple[Path, Path]:
    """Write a short-lived certificate for 127.0.0.1 and return ``(cert, key)``."""
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1,DNS:localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def _append_log(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def _country_from(pairs: list[list[str]]) -> str:
    for key, value in pairs:
        if key.lower() == "x-proxymesh-country" and "\r" not in value and "\n" not in value:
            return value
    return ""


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    log_path: Path,
) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, ConnectionError):
        writer.close()
        return
    text = head.decode("iso-8859-1", "replace")
    lines = text.split("\r\n")
    parts = lines[0].split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    pairs: list[list[str]] = []
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        pairs.append([key.strip(), value.strip()])
    _append_log(log_path, {"method": method, "target": target, "headers": pairs})
    if method != "CONNECT":
        body = b"method not allowed"
        writer.write(
            b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        return
    host, port_text = target.rsplit(":", 1)
    country = _country_from(pairs)
    remote_reader, remote_writer = await asyncio.open_connection(host, int(port_text))
    response = (
        "HTTP/1.1 200 Connection established\r\n"
        "X-Test-Proxy: 1\r\n"
        f"X-Echo-Country: {country}\r\n"
        "\r\n"
    )
    writer.write(response.encode("ascii"))
    await writer.drain()
    await asyncio.gather(_pipe(reader, remote_writer), _pipe(remote_reader, writer))


def start_connect_proxy(log_path: Path) -> tuple[int, Callable[[], None]]:
    """Start an asyncio CONNECT proxy on 127.0.0.1 and return ``(port, stop)``."""
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    holder: dict[str, Any] = {}
    errors: list[BaseException] = []

    def runner() -> None:
        asyncio.set_event_loop(loop)

        async def main() -> None:
            async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                await _handle_client(reader, writer, log_path)

            server = await asyncio.start_server(client, "127.0.0.1", 0)
            holder["server"] = server
            ready.set()
            async with server:
                await server.serve_forever()

        try:
            loop.run_until_complete(main())
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            errors.append(exc)
            ready.set()

    thread = threading.Thread(target=runner, name="connect-proxy", daemon=True)
    thread.start()
    if not ready.wait(10):
        raise RuntimeError("CONNECT proxy did not start")
    if errors:
        raise RuntimeError(f"CONNECT proxy failed: {errors[0]}")
    sockets = holder["server"].sockets
    port = sockets[0].getsockname()[1]

    def stop() -> None:
        server = holder.get("server")
        if server is not None:
            loop.call_soon_threadsafe(server.close)

    return port, stop


class _TargetHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        payload = {
            "headers": dict(self.headers.items()),
            "request_version": self.request_version,
            "close_connection": self.close_connection,
        }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def start_https_target(cert: Path, key: Path) -> tuple[int, Callable[[], None]]:
    """Start a TLS HTTP server on 127.0.0.1 and return ``(port, stop)``."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TargetHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, name="https-target", daemon=True)
    thread.start()
    port = server.server_address[1]

    def stop() -> None:
        server.shutdown()
        server.server_close()

    return port, stop


def read_proxy_log(path: Path) -> list[dict[str, Any]]:
    """Return JSON events written by the CONNECT proxy."""
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events
