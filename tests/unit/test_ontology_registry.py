"""Unit tests for the ``OntologyRegistry``."""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from rdflib.compare import isomorphic

from core import FormatOntology
from service.ontology_registry import OntologyRegistry

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
    async def test_invalid_file_raises_value_error(self, registry: OntologyRegistry, tmp_path: Path) -> None:
        path = tmp_path / "bad.ttl"
        path.write_text("this is not rdf")
        with pytest.raises(ValueError):
            await registry.resolve(path.as_uri())

    async def test_missing_file_raises_file_not_found(self, registry: OntologyRegistry, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            await registry.resolve((tmp_path / "missing.owl").as_uri())


class TestHttpScheme:
    async def test_http_error_status_raises(self, registry: OntologyRegistry, mock_http) -> None:
        mock_http(lambda r: httpx.Response(404))
        with pytest.raises(httpx.HTTPError):
            await registry.resolve("http://example.org/missing.owl")

    async def test_unparseable_body_raises_value_error(self, registry: OntologyRegistry, mock_http) -> None:
        mock_http(lambda r: httpx.Response(200, content=b"this is not rdf"))
        with pytest.raises(ValueError):
            await registry.resolve("http://example.org/schema.ttl")


class TestCaching:
    @pytest.fixture
    def turtle(self, serialise_example) -> bytes:
        return serialise_example("turtle")

    async def test_second_resolve_is_cached(self, registry: OntologyRegistry, mock_http, turtle: bytes) -> None:
        requests = mock_http(lambda r: httpx.Response(200, content=turtle))
        first = await registry.resolve("http://example.org/schema.ttl")
        second = await registry.resolve("http://example.org/schema.ttl")
        assert first is second
        assert len(requests) == 1

    async def test_clear_cache_forces_refetch(self, registry: OntologyRegistry, mock_http, turtle: bytes) -> None:
        requests = mock_http(lambda r: httpx.Response(200, content=turtle))
        first = await registry.resolve("http://example.org/schema.ttl")
        registry.clear_cache()
        second = await registry.resolve("http://example.org/schema.ttl")
        assert first is not second
        assert len(requests) == 2


class TestSerialisations:
    """The example ontology resolves the same in every supported serialisation."""

    @staticmethod
    def _assert_same_ontology(actual: FormatOntology, expected: FormatOntology) -> None:
        """``actual`` holds exactly the triples of ``expected``."""
        assert isomorphic(actual.graph, expected.graph)

    async def test_file_by_extension(
        self, registry: OntologyRegistry, tmp_path: Path, example_serialisation, example_ontology: FormatOntology
    ) -> None:
        extension, content = example_serialisation
        path = tmp_path / f"example{extension}"
        path.write_bytes(content)
        actual = await registry.resolve(path.as_uri())
        self._assert_same_ontology(actual, expected=example_ontology)

    async def test_http_by_extension(
        self, registry: OntologyRegistry, mock_http, example_serialisation, example_ontology: FormatOntology
    ) -> None:
        extension, content = example_serialisation
        mock_http(lambda r: httpx.Response(200, content=content))
        actual = await registry.resolve(f"http://example.org/formats{extension}")
        self._assert_same_ontology(actual, expected=example_ontology)

    @pytest.mark.parametrize(
        ("content_type", "rdf_format"),
        [
            ("application/rdf+xml", "xml"),
            ("application/xml", "xml"),
            ("text/xml", "xml"),
            ("text/turtle", "turtle"),
            ("application/n-triples", "nt"),
            ("text/n3", "n3"),
            ("application/ld+json", "json-ld"),
            ("application/ld+json; charset=utf-8", "json-ld"),
        ],
    )
    async def test_http_by_content_type(
        self,
        registry: OntologyRegistry,
        mock_http,
        serialise_example,
        example_ontology: FormatOntology,
        content_type: str,
        rdf_format: str,
    ) -> None:
        content = serialise_example(rdf_format)
        mock_http(lambda r: httpx.Response(200, content=content, headers={"content-type": content_type}))
        actual = await registry.resolve("http://example.org/formats")
        self._assert_same_ontology(actual, expected=example_ontology)
