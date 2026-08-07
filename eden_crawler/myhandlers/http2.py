import asyncio
import socket
import ssl
from urllib.parse import urlparse

import h2.config
import h2.connection
import h2.events
from scrapy.http import HtmlResponse


def _tunnel_proxy(host, port, proxy_url, timeout):
    """CONNECT tunnel through HTTP proxy. Returns a socket connected to target via proxy."""
    parsed = urlparse(proxy_url)
    sock = socket.create_connection((parsed.hostname, parsed.port or 8080), timeout=timeout)
    connect = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n"
    sock.sendall(connect.encode())
    resp = sock.recv(4096)
    if b"200" not in resp.split(b"\r\n")[0]:
        raise ConnectionError(f"Proxy CONNECT failed: {resp.decode()}")
    return sock


class H2DownloadHandler:
    lazy = False

    def __init__(self, settings):
        self._timeout = settings.getfloat("DOWNLOAD_TIMEOUT", 30)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    async def download_request(self, request):
        return await asyncio.to_thread(self._fetch, request)

    def _fetch(self, request):
        parsed = urlparse(request.url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        proxy = request.meta.get("proxy")

        if parsed.scheme == "https" and proxy:
            sock = _tunnel_proxy(host, port, proxy, self._timeout)
        else:
            sock = socket.create_connection((host, port), timeout=self._timeout)

        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.set_alpn_protocols(["h2"])
            sock = ctx.wrap_socket(sock, server_hostname=host)

        cfg = h2.config.H2Configuration(client_side=True)
        conn = h2.connection.H2Connection(config=cfg)
        conn.initiate_connection()
        sock.sendall(conn.data_to_send())

        hdrs = [
            (":method", request.method),
            (":path", path),
            (":authority", host),
            (":scheme", parsed.scheme),
        ]
        for k, v in request.headers.items():
            key = k.decode().lower()
            if key not in (
                ":method", ":path", ":authority", ":scheme",
                "host", "content-length",
            ):
                hdrs.append((key, v[0].decode()))

        stream_id = conn.get_next_available_stream_id()
        conn.send_headers(stream_id, hdrs, end_stream=not request.body)
        sock.sendall(conn.data_to_send())
        if request.body:
            conn.send_data(stream_id, request.body, end_stream=True)
            sock.sendall(conn.data_to_send())

        resp_headers = {}
        resp_data = bytearray()
        resp_status = 0

        try:
            while True:
                data = sock.recv(65535)
                if not data:
                    break
                for event in conn.receive_data(data):
                    if isinstance(event, h2.events.ResponseReceived):
                        resp_headers = {h.decode(): v.decode() for h, v in event.headers}
                        resp_status = int(resp_headers.get(":status", 0))
                    elif isinstance(event, h2.events.DataReceived):
                        resp_data.extend(event.data)
                        conn.acknowledge_received_data(
                            event.flow_controlled_length, event.stream_id
                        )
                    elif isinstance(event, h2.events.StreamEnded):
                        sock.sendall(conn.data_to_send())
                        conn.close_connection()
                        sock.sendall(conn.data_to_send())
                        sock.close()
                        return HtmlResponse(
                            url=request.url,
                            status=resp_status,
                            headers=resp_headers,
                            body=bytes(resp_data),
                            request=request,
                        )
                sock.sendall(conn.data_to_send())
        finally:
            try:
                sock.close()
            except OSError:
                pass

        # Server closed connection without completing HTTP/2 stream
        if resp_status:
            return HtmlResponse(
                url=request.url,
                status=resp_status,
                headers=resp_headers,
                body=bytes(resp_data),
                request=request,
            )
        raise ConnectionError(f"H2 server closed connection before response: {request.url}")

    async def close(self):
        pass
