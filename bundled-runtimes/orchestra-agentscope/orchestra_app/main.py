import os

import uvicorn

from .api import app


if __name__ == "__main__":
    uvicorn.run(
        "orchestra_app.api:app",
        host=os.getenv("ORCHESTRA_API_HOST", "127.0.0.1"),
        port=int(os.getenv("ORCHESTRA_API_PORT", "8001")),
        reload=os.getenv("ORCHESTRA_API_RELOAD", "false").lower() == "true",
    )
