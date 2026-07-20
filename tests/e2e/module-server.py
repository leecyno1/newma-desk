from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
MOUNTS = {
    "/modules/demo": ROOT / "tests" / "e2e" / "fixtures" / "modules" / "demo",
    "/modules/market-daily": ROOT / "modules" / "market-daily" / "dist",
}


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path).rstrip("/")
        for prefix, root in MOUNTS.items():
            if request_path == prefix:
                return str(root)
            if request_path.startswith(f"{prefix}/"):
                relative = request_path[len(prefix) + 1 :]
                candidate = (root / relative).resolve()
                if root.resolve() in candidate.parents:
                    return str(candidate)
        return str(ROOT / "tests" / "e2e" / "fixtures" / "not-found")

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    arguments = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
