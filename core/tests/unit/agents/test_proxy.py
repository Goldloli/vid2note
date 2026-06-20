import asyncio

from vid2note_core.agents.proxy import AllowlistConnectProxy


def test_proxy_relays_only_allowlisted_connect_target():
    async def scenario():
        async def echo(reader, writer):
            writer.write(await reader.read(4))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        proxy = AllowlistConnectProxy({("127.0.0.1", upstream_port)})
        await proxy.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
            writer.write(f"CONNECT 127.0.0.1:{upstream_port} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            assert await reader.readline() == b"HTTP/1.1 200 Connection Established\r\n"
            assert await reader.readline() == b"\r\n"
            writer.write(b"ping")
            await writer.drain()
            assert await reader.readexactly(4) == b"ping"
            writer.close()
            await writer.wait_closed()

            denied_reader, denied_writer = await asyncio.open_connection("127.0.0.1", proxy.port)
            denied_writer.write(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
            await denied_writer.drain()
            assert await denied_reader.readline() == b"HTTP/1.1 403 Forbidden\r\n"
            denied_writer.close()
            await denied_writer.wait_closed()
        finally:
            await proxy.close()
            upstream.close()
            await upstream.wait_closed()

    asyncio.run(scenario())
