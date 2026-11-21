from contextlib import closing
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


def database_is_ready() -> bool:
    with closing(HTTPConnection("database", 8081, timeout=2)) as connection:
        try:
            connection.request("GET", "/health")
            with connection.getresponse() as response:
                return response.status == HTTPStatus.OK
        except (OSError, HTTPException):
            return False


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            service, ready = "backend", True
        elif self.path == "/health/database":
            service, ready = "database", database_is_ready()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
        payload = {"status": "ok" if ready else "unavailable", "service": service}
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    with ThreadingHTTPServer(("0.0.0.0", 8000), HealthHandler) as server:
        print("Backend lauscht auf Port 8000.")
        server.serve_forever()
