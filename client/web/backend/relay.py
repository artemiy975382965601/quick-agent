"""TCP-релей для туннеля: 192.168.31.99:8081 -> 127.0.0.1:8080.

Нужен потому, что веб-бэкенд слушает только loopback, а cloudflared
запускается в отдельном network namespace (там свой сетевой стек и 127.0.0.1
принадлежит ему, а не хосту).
"""
import asyncio
import sys

LISTEN = [("10.77.0.1", 8081), ("192.168.31.99", 8081)]
TARGET = ("127.0.0.1", 8090)


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    try:
        up_reader, up_writer = await asyncio.open_connection(*TARGET)
    except Exception:
        client_writer.close()
        return
    await asyncio.gather(
        pipe(client_reader, up_writer),
        pipe(up_reader, client_writer),
    )


async def main() -> None:
    servers = [await asyncio.start_server(handle, *addr) for addr in LISTEN]
    for s_ in servers:
        print(f"relay {s_.sockets[0].getsockname()[:2]} -> {TARGET}", flush=True)
    await asyncio.gather(*(s_.serve_forever() for s_ in servers))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
