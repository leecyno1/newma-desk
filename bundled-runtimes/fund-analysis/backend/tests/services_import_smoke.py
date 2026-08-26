import importlib
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def main() -> int:
    handler = CaptureHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        import services
        importlib.reload(services)
    finally:
        root.removeHandler(handler)

    wind_messages = [message for message in handler.messages if "Wind Python API not available" in message]
    if wind_messages:
        print(f"Expected import services to avoid eager Wind import, got: {wind_messages}")
        return 1

    print("OK services import")
    return 0


if __name__ == "__main__":
    sys.exit(main())
