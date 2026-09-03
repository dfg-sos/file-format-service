"""Service for fetching, parsing, and caching OWL ontologies by schema URL."""

from pathlib import Path
from urllib.parse import urlparse

import httpx

from compatibility import FormatOntology


class OntologyRegistry:
    """Fetches, parses, and caches OWL ontologies by schema URL."""

    def __init__(self):
        self._cache: dict[str, FormatOntology] = {}

    async def resolve(self, schema_url: str) -> FormatOntology:
        """Fetch and parse an ontology, or return a cached instance.

        Supports ``http://``, ``https://``, and ``file://`` URLs.

        Args:
            schema_url: URL pointing to the OWL/RDF ontology schema.

        Returns:
            A populated ``FormatOntology`` with namespace inference already
            applied.
        """
        if schema_url in self._cache:
            return self._cache[schema_url]

        parsed = urlparse(schema_url)
        if parsed.scheme == "file":
            # Let rdflib infer the serialisation format from the file extension.
            path = Path(parsed.path)
            ontology = FormatOntology.from_source(path)
            self._cache[schema_url] = ontology
            return ontology

        async with httpx.AsyncClient() as client:
            response = await client.get(schema_url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            content = response.content

        # Try to determine RDF format from Content-Type or URL extension.
        content_type = response.headers.get("content-type", "")
        format_hint: str | None = None
        if "xml" in content_type or schema_url.endswith(".owl") or schema_url.endswith(".rdf"):
            format_hint = "xml"
        elif "turtle" in content_type or schema_url.endswith(".ttl"):
            format_hint = "turtle"

        ontology = FormatOntology.from_bytes(content, format=format_hint)
        self._cache[schema_url] = ontology
        return ontology

    def clear_cache(self) -> None:
        """Drop all cached ontologies."""
        self._cache.clear()