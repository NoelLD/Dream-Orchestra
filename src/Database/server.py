from contextlib import closing
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3


DATABASE_PATH = Path("/data/dreamorchestra.sqlite3")
SCHEMA_PATH = Path("/schema/schema.sql")


def initialize_database() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.executescript(f"BEGIN;\n{schema}\nCOMMIT;")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            with closing(sqlite3.connect(f"{DATABASE_PATH.as_uri()}?mode=ro", uri=True)) as connection:
                connection.execute("SELECT count(*) FROM sqlite_schema").fetchone()
        except sqlite3.Error:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "SQLite unavailable")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Length", "0")
        self.end_headers()


if __name__ == "__main__":
    initialize_database()
    with ThreadingHTTPServer(("0.0.0.0", 8081), HealthHandler) as server:
        print("SQLite-Datenbank bereit.")
        server.serve_forever()
