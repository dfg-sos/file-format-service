"""Service for fetching, parsing, and caching OWL ontologies by schema URL."""

from pathlib import Path
from urllib.parse import urlparse

import httpx
from rdflib.util import guess_format

from core import FormatOntology

# Media types of the RDF serialisations, mapped to rdflib format names.
_MEDIA_TYPE_FORMATS = {
    "application/rdf+xml": "xml",
    "application/xml": "xml",
    "text/xml": "xml",
    "text/turtle": "turtle",
    "application/n-triples": "nt",
    "text/n3": "n3",
    "application/ld+json": "json-ld",
}


class OntologyRegistry:
    """Fetches, parses, and caches OWL ontologies by schema URL."""

    def __init__(self):
        self._cache: dict[str, FormatOntology] = {}

    async def resolve(self, schema_url: str) -> FormatOntology:
        """Fetch and parse an ontology, or return a cached instance.

        Supports ``http://``, ``https://``, and ``file://`` URLs and the RDF
        serialisations RDF/XML, Turtle, N-Triples, N3 and JSON-LD. The format
        is taken from the file extension for ``file://`` URLs, and from the
        Content-Type, else the URL extension, for HTTP(S).

        Args:
            schema_url: URL pointing to the OWL/RDF ontology schema.

        Returns:
            A populated ``FormatOntology`` with namespace inference already
            applied.

        Raises:
            FileNotFoundError: When a ``file://`` URL points to no file.
            httpx.HTTPError: When the schema URL cannot be fetched.
            ValueError: When the fetched content cannot be parsed as RDF.
        """
        if schema_url in self._cache:
            return self._cache[schema_url]

        parsed = urlparse(schema_url)
        if parsed.scheme == "file":
            # Let rdflib infer the serialisation format from the file extension.
            path = Path(parsed.path)
            if not path.is_file():
                raise FileNotFoundError(f"Ontology schema not found: {schema_url}")
            try:
                ontology = FormatOntology.from_source(path)
            except Exception as exc:
                raise ValueError(f"Could not parse ontology from {schema_url}: {exc}") from exc
            self._cache[schema_url] = ontology
            return ontology

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(schema_url, timeout=30.0, follow_redirects=True)
                response.raise_for_status()
                content = response.content
        except httpx.HTTPError as exc:
            raise httpx.HTTPError(f"Could not fetch ontology from {schema_url}: {exc}") from exc

        # Determine the RDF format from the Content-Type, else from the URL
        # extension. Without either, rdflib tries Turtle.
        media_type = response.headers.get("content-type", "").partition(";")[0].strip().lower()
        format_hint = _MEDIA_TYPE_FORMATS.get(media_type) or guess_format(parsed.path)

        try:
            ontology = FormatOntology.from_bytes(content, format=format_hint)
        except Exception as exc:
            raise ValueError(f"Could not parse ontology from {schema_url}: {exc}") from exc

        self._cache[schema_url] = ontology
        return ontology

    def clear_cache(self) -> None:
        """Drop all cached ontologies."""
        self._cache.clear()
