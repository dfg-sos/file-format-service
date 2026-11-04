import logging

# The service's own log messages and the validator's (loaded plugins, formats, loaded mappings),
# in uvicorn's format. Configured before the imports: format_validator loads its plugins on import.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

from api.app import create_app  # noqa: E402
from config import Settings  # noqa: E402

settings = Settings()
app = create_app(settings)
