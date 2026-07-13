import argparse
import http.client
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


class WorkbenchHandler(SimpleHTTPRequestHandler):
    api_origin = "http://127.0.0.1:8791"

    def _proxy_api(self):
        origin = urlsplit(self.api_origin)
        connection_class = (
            http.client.HTTPSConnection
            if origin.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_class(origin.hostname, origin.port, timeout=180)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "content-length"}
        }
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        finally:
            connection.close()

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
            return
        self.send_error(405, "POST is only available under /api/")


def main():
    parser = argparse.ArgumentParser(description="Serve Pages assets with a local Worker API proxy")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--api-origin", default="http://127.0.0.1:8791")
    parser.add_argument("--public-dir", type=Path, default=ROOT / "public")
    args = parser.parse_args()

    WorkbenchHandler.api_origin = args.api_origin
    handler = partial(WorkbenchHandler, directory=str(args.public_dir.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Workbench dev server: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
