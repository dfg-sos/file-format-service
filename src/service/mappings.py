"""Load the mapping files from ontology format identifiers to validator formats."""

import logging
from pathlib import Path

from format_validator import FormatTranslator

logger = logging.getLogger(__name__)


def load_format_translator(mappings_dir: Path) -> FormatTranslator:
    """Load the mapping files (``*.json``) in ``mappings_dir`` into one translator.

    Each file maps the format identifiers of the ontology ``ontology_uri`` to
    validator format identifiers (see ``FormatTranslator.from_json``). The
    translator is keyed by the full format IRI, ``ontology_uri`` followed by
    the identifier. A missing or empty directory yields a translator without
    mappings, which rejects every format; this is logged as a warning.

    Raises:
        ValueError: A file is invalid, two files map the same IRI to different
            formats, or a file maps to a format identifier the validator does
            not know; the message names the file.
    """
    translator = FormatTranslator.from_directory(mappings_dir)
    files = sorted(path.name for path in mappings_dir.glob("*.json"))
    if files:
        logger.info("Loaded format mappings from %s: %d formats", ", ".join(files), len(translator.iris()))
    else:
        logger.warning("No mapping files (*.json) found in %s, validation rejects every format", mappings_dir)
    return translator
