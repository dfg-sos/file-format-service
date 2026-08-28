"""Uvicorn entrypoint for the SOS File Format Service."""

import uvicorn

from api.app import create_app
from config import Settings


def main() -> None:
    settings = Settings()
    app = create_app(settings)
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
