  Let me document all the proposed changes for the dynamic ontology feature in a structured plan.

---

## Plan: Dynamic Ontology via Schema URL with Inferred Namespace

### Overview
Remove the hard dependency on a local ontology file. Each request to `/compatibility` supplies only an `ontology_schema_url`. The service:
1. Fetches the OWL file asynchronously via `httpx`
2. Parses it with `rdflib`
3. **Infers the namespace** from the parsed ontology
4. Caches the resulting `FormatOntology` by schema URL
5. Uses the inferred namespace for ID expansion

---

### 1. `pyproject.toml` — Move `httpx` to main dependencies

**Current:**
```toml
[project]
dependencies = [
    "aiofiles",
    "rdflib",
    "format-validator @ git+...",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "pytest-cov",
    "httpx>=0.27",
    "ruff",
    "mypy>=1.10",
]
```

**Change:** Move `"httpx>=0.27"` from `dev` to main `dependencies`.

---

### 2. `src/compatibility/ontology.py` — Refactor `FormatOntology`

**Changes:**
- Remove module-level `_expand_id()` function and `EDAM_NAMESPACE`
- Add `from __future__ import annotations` is already present
- Add missing `RDF` import (needed for `RDF.type`)
- Change `__init__` to accept a pre-populated `Graph` and optional `namespace`
- Add `from_source(cls, ...)` classmethod for loading from file/URI
- Add `from_bytes(cls, ...)` classmethod for parsing raw bytes
- Add `_infer_namespace()` instance method to derive namespace from graph
- Convert `_expand_id()` to instance method using inferred namespace
- Update `is_subclass()`, `get_parents()`, `get_equivalents()` to use `self._expand_id()`

**New structure:**
```python
class FormatOntology:
    def __init__(self, graph: Optional[Graph] = None, namespace: Optional[str] = None):
        self.graph = graph or Graph()
        self._namespace = namespace or self._infer_namespace()
    
    @classmethod
    def from_source(cls, ontology_source: str | Path) -> "FormatOntology": ...
    
    @classmethod
    def from_bytes(cls, data: bytes, format: Optional[str] = None) -> "FormatOntology": ...
    
    def _infer_namespace(self) -> Optional[str]: ...
    def _expand_id(self, fmt: str) -> str: ...
    # ... rest unchanged except using self._expand_id
```

---

### 3. `src/service/ontology_registry.py` — New file

Create a new service that fetches and caches ontologies:

```python
"""Service for fetching, parsing, and caching OWL ontologies by schema URL."""
import httpx
from compatibility import FormatOntology

class OntologyRegistry:
    """Fetches, parses, and caches OWL ontologies by schema URL."""

    def __init__(self):
        self._cache: dict[str, FormatOntology] = {}

    async def resolve(self, schema_url: str) -> FormatOntology:
        if schema_url in self._cache:
            return self._cache[schema_url]

        async with httpx.AsyncClient() as client:
            response = await client.get(schema_url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            content = response.content

        ontology = FormatOntology.from_bytes(content)
        self._cache[schema_url] = ontology
        return ontology

    def clear_cache(self) -> None:
        self._cache.clear()
```

---

### 4. `src/service/compatibility_service.py` — Make stateless

**Changes:**
- Remove `__init__`, `_load_ontology()`, `self.settings`, `self._ontology`
- Make `check()`, `get_parents()`, `get_equivalents()` static/class methods
- `check()` now accepts a `FormatOntology` instance directly
- Add type hints

**New structure:**
```python
class CompatibilityService:
    @staticmethod
    def check(expected: str, actual: str, ontology: FormatOntology) -> CompatibilityResult: ...

    @staticmethod
    def get_parents(fmt: str, ontology: FormatOntology) -> list[str]: ...

    @staticmethod
    def get_equivalents(fmt: str, ontology: FormatOntology) -> list[str]: ...
```

---

### 5. `src/config.py` — Remove ontology file settings

**Remove:**
- `ontology_path: Path = Path("ontology/edamontology_adapted.org.owl")`
- `default_ontology_uri: str = "http://edamontology.org"`

**Keep:**
- `mappings_dir`
- `app_name`, `app_version`, `host`, `port`

---

### 6. `src/api/dependencies.py` — Add registry, remove service dep

**Changes:**
- Remove `get_compatibility_service()`
- Add `get_ontology_registry()` (cached singleton)
- Add `resolve_ontology(schema_url: str, registry: OntologyRegistry)` async dependency

**New imports needed:**
```python
from service.ontology_registry import OntologyRegistry
from compatibility import FormatOntology
```

---

### 7. `src/api/schemas/compatibility.py` — Replace `ontology_uri` with `ontology_schema_url`

**Current:**
```python
class CompatibilityRequest(BaseModel):
    expected_format: str
    actual_format: str
    ontology_uri: str = Field(default="http://edamontology.org", ...)
```

**New:**
```python
class CompatibilityRequest(BaseModel):
    expected_format: str
    actual_format: str
    ontology_schema_url: str = Field(..., description="URL to the OWL/RDF ontology schema file.")
```

**Keep `CompatibilityResponse` unchanged.**

---

### 8. `src/api/routers/compatibility.py` — Use registry-based resolution

**Changes:**
- Remove `get_compatibility_service` dependency
- Add `resolve_ontology` dependency (injected via `Depends`)
- Pass resolved `ontology: FormatOntology` to `CompatibilityService.check()`

**New endpoint:**
```python
@router.post("/compatibility")
async def check_compatibility(
    request: CompatibilityRequest,
    ontology: FormatOntology = Depends(resolve_ontology),
) -> CompatibilityResponse:
    result = CompatibilityService.check(
        expected=request.expected_format,
        actual=request.actual_format,
        ontology=ontology,
    )
    return CompatibilityResponse(...)
```

---

### 9. `src/api/routers/validation.py` — No changes needed

The validation endpoint uses `FormatTranslator` with JSON mapping files, not the OWL ontology. `ontology_uri` remains as a form parameter for mapping lookup.

---

### 10. `tests/unit/test_compatibility.py` — Update for stateless service

**Current:**
```python
@pytest.fixture
def service(self) -> CompatibilityService:
    settings = Settings()
    return CompatibilityService(settings)
```

**New:** Construct `FormatOntology` directly from the local file and pass it to `CompatibilityService.check()`:
```python
@pytest.fixture
def ontology(self) -> FormatOntology:
    return FormatOntology.from_source("ontology/edamontology_adapted.org.owl")
```

Update test calls:
```python
result = CompatibilityService.check(expected="...", actual="...", ontology=ontology)
```

---

### 11. `tests/integration/test_api.py` — Remove formats tests, update compatibility

**Remove:**
- `class TestFormatsEndpoint` entirely

**Update `TestCompatibilityEndpoint`:**
- Replace `ontology_uri` with `ontology_schema_url` pointing to a local `file://` URI for the test

```python
def test_compatibility_same_format(self, client: TestClient) -> None:
    payload = {
        "expected_format": "format_4119",
        "actual_format": "format_4119",
        "ontology_schema_url": "file://" + str(Path("ontology/edamontology_adapted.org.owl").resolve()),
    }
    response = client.post("/api/v1/compatibility", json=payload)
    ...
```

---

### 12. README — Update compatibility endpoint docs

After implementation, update the README to:
- Remove `ontology_path` and `default_ontology_uri` from the config table
- Update the `/compatibility` example to show `ontology_schema_url`
- Update the architecture overview to mention `OntologyRegistry`

---

### File Summary

| File | Action |
|------|--------|
| `pyproject.toml` | Move `httpx` to main deps |
| `src/compatibility/ontology.py` | Refactor `FormatOntology` (instance methods, classmethods, namespace inference) |
| `src/service/ontology_registry.py` | **New file** — async fetch + cache |
| `src/service/compatibility_service.py` | Make stateless, accept `FormatOntology` |
| `src/config.py` | Remove `ontology_path`, `default_ontology_uri` |
| `src/api/dependencies.py` | Add `OntologyRegistry` dependency, remove `CompatibilityService` dep |
| `src/api/schemas/compatibility.py` | Replace `ontology_uri` → `ontology_schema_url` |
| `src/api/routers/compatibility.py` | Use `resolve_ontology` dependency |
| `tests/unit/test_compatibility.py` | Update fixtures and calls |
| `tests/integration/test_api.py` | Remove formats tests, update compatibility payload |
| `README.md` | Update docs (post-implementation) |