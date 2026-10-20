"""Unit tests for the ``OntologyRegistry``."""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from core import FormatOntology
from service.ontology_registry import OntologyRegistry

from .conftest import TOY_TTL

TOY_OWL = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#">
  <owl:Ontology rdf:about="http://example.org/"/>
  <owl:Class rdf:about="http://example.org/vector"/>
</rdf:RDF>
"""

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def registry() -> OntologyRegistry:
    return OntologyRegistry()


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], list[httpx.Request]]:
    """Route all ``httpx.AsyncClient`` traffic to a handler; return the recorded requests."""
    real_client = httpx.AsyncClient

    def install(handler: Handler) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(recording), **kwargs),
        )
        return requests

    return install


class TestFileScheme:
    async def test_resolves_local_file(self, registry: OntologyRegistry, tmp_path: Path) -> None:
        path = tmp_path / "toy.ttl"
        path.write_bytes(TOY_TTL)
        ontology = await registry.resolve(path.as_uri())
        assert isinstance(ontology, FormatOntology)
        assert ontology.is_defined("vector")

    async def test_invalid_file_raises_value_error(self, registry: OntologyRegistry, tmp_path: Path) -> None:
        path = tmp_path / "bad.ttl"
        path.write_text("this is not rdf")
        with pytest.raises(ValueError):
            await registry.resolve(path.as_uri())

    async def test_missing_file_raises_file_not_found(self, registry: OntologyRegistry, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            await registry.resolve((tmp_path / "missing.owl").as_uri())


class TestHttpScheme:
    async def test_turtle_from_content_type(self, registry: OntologyRegistry, mock_http) -> None:
        mock_http(lambda r: httpx.Response(200, content=TOY_TTL, headers={"content-type": "text/turtle"}))
        ontology = await registry.resolve("http://example.org/schema")
        assert ontology.is_defined("vector")

    async def test_turtle_from_extension(self, registry: OntologyRegistry, mock_http) -> None:
        mock_http(lambda r: httpx.Response(200, content=TOY_TTL))
        ontology = await registry.resolve("http://example.org/schema.ttl")
        assert ontology.is_defined("vector")

    async def test_owl_from_extension(self, registry: OntologyRegistry, mock_http) -> None:
        mock_http(lambda r: httpx.Response(200, content=TOY_OWL))
        ontology = await registry.resolve("http://example.org/schema.owl")
        assert ontology.is_defined("vector")

    async def test_http_error_status_raises(self, registry: OntologyRegistry, mock_http) -> None:
        mock_http(lambda r: httpx.Response(404))
        with pytest.raises(httpx.HTTPError):
            await registry.resolve("http://example.org/missing.owl")

    async def test_unparseable_body_raises_value_error(self, registry: OntologyRegistry, mock_http) -> None:
        mock_http(lambda r: httpx.Response(200, content=b"this is not rdf"))
        with pytest.raises(ValueError):
            await registry.resolve("http://example.org/schema.ttl")


class TestCaching:
    async def test_second_resolve_is_cached(self, registry: OntologyRegistry, mock_http) -> None:
        requests = mock_http(lambda r: httpx.Response(200, content=TOY_TTL))
        first = await registry.resolve("http://example.org/schema.ttl")
        second = await registry.resolve("http://example.org/schema.ttl")
        assert first is second
        assert len(requests) == 1

    async def test_clear_cache_forces_refetch(self, registry: OntologyRegistry, mock_http) -> None:
        requests = mock_http(lambda r: httpx.Response(200, content=TOY_TTL))
        first = await registry.resolve("http://example.org/schema.ttl")
        registry.clear_cache()
        second = await registry.resolve("http://example.org/schema.ttl")
        assert first is not second
        assert len(requests) == 2
