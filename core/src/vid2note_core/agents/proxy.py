from __future__ import annotations

import asyncio
from contextlib import suppress


class AllowlistConnectProxy:
    def __init__(self, allowed_targets: set[tuple[str, int]]):
        self.allowed_targets = {(host.casefold(), port) for host, port in allowed_targets}
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("proxy_not_started")
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            request = (await reader.readline()).decode("ascii", errors="replace").strip()
            parts = request.split()
            if len(parts) != 3 or parts[0] != "CONNECT":
                await self._respond(writer, "405 Method Not Allowed")
                return
            try:
                host, raw_port = parts[1].rsplit(":", 1)
                port = int(raw_port)
            except (TypeError, ValueError):
                await self._respond(writer, "400 Bad Request")
                return
            header_bytes = 0
            while line := await reader.readline():
                header_bytes += len(line)
                if header_bytes > 65536:
                    await self._respond(writer, "431 Request Header Fields Too Large")
                    return
                if line in {b"\r\n", b"\n"}:
                    break
            if (host.casefold(), port) not in self.allowed_targets:
                await self._respond(writer, "403 Forbidden")
                return
            try:
                upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
            except OSError:
                await self._respond(writer, "502 Bad Gateway")
                return
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            client_to_upstream = asyncio.create_task(self._pipe(reader, upstream_writer))
            upstream_to_client = asyncio.create_task(self._pipe(upstream_reader, writer))
            done, pending = await asyncio.wait(
                {client_to_upstream, upstream_to_client},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        finally:
            if upstream_writer is not None:
                upstream_writer.close()
                with suppress(OSError):
                    await upstream_writer.wait_closed()
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    @staticmethod
    async def _respond(writer: asyncio.StreamWriter, status: str) -> None:
        writer.write(f"HTTP/1.1 {status}\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()

    @staticmethod
    async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
