# SOS File Format Service

A FastAPI REST API service for validating Earth Observation (EO) file formats and checking ontology-based format compatibility.

The service bridges ontology-specific format identifiers (e.g. from the EDAM ontology) with an external `format_validator` module, enabling automated validation of uploaded geospatial files. Furthermore static compatibility checks can be executed upon existing OWL/RDF ontologies.

## Features

- **File Format Validation** — Upload a file and validate it against a required format using multiple validation modes (`basic`, `structural`, `full`). `full` mode also validates file metadata against optional expected values.
- **Dynamic Ontology-based Compatibility Checks** — Check whether one format is compatible with another by evaluating `rdfs:subClassOf` and `owl:equivalentClass` relationships in any user-supplied OWL/RDF ontology.
- **Remote Ontology Support** — Ontologies are fetched on demand from a provided schema URL and cached in memory for subsequent requests.

## Architecture Overview

The service follows a layered architecture:

- **API Layer** (`api/`) — FastAPI routers, Pydantic request/response schemas, and exception handlers.
- **Service Layer** (`service/`) — Business logic, including `CompatibilityService` for ontology queries and `OntologyRegistry` for fetching and caching remote ontologies.
- **Adapter Layer** (`adapter/`) — Bridges between HTTP API types and the external `format_validator` module (`HTTPValidationRequestBuilder`, `HTTPValidationResponseHandler`).
- **Compatibility Layer** (`compatibility/`) — OWL/RDF ontology parsing and reasoning using `rdflib` (`FormatOntology`, `CompatibilityResult`).
- **Configuration** (`config.py`) — Pydantic-settings based configuration with environment variable support.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check probe |
| `POST` | `/api/v1/validate` | Validate an uploaded file against a required format |
| `POST` | `/api/v1/compatibility` | Check compatibility between two format identifiers |
| `POST` | `/api/v1/format-info` | Retrieve detailed metadata for a format from an ontology |

### Example: Validate a File

```bash
curl -X POST "http://localhost:8000/api/v1/validate" \
  -F "file=@/path/to/your/file.geojson" \
  -F "ontology_namespace=http://edamontology.org" \
  -F "format_identifier=format_4106" \
  -F "mode=full"
```

> **Note:** The validation endpoint expects `ontology_namespace` (the ontology's base URI, used for format mapping lookup), while the compatibility endpoint expects `ontology_schema_url` (the URL to the actual OWL/RDF schema file).

In `full` mode, additional optional fields let you validate a file's metadata against an expected value. For EO these include: `expected_crs` (any coordinate reference system string understood by `pyproj`, e.g. `EPSG:4326`) and `expected_geometry_type` (a GeoJSON-style geometry type such as `Point` or `MultiPolygon`, matched case-insensitively; only applies to vector formats). Omitting either field skips that check.

### Example: Check Compatibility

```bash
curl -X POST "http://localhost:8000/api/v1/compatibility" \
  -H "Content-Type: application/json" \
  -d '{
    "expected_format": "format_4126",
    "actual_format": "format_4119",
    "ontology_schema_url": "https://example.org/ontology.owl"
  }'
```

### Example: Format Info

```bash
curl -X POST "http://localhost:8000/api/v1/format-info" \
  -H "Content-Type: application/json" \
  -d '{
    "format_identifier": "format_4119",
    "ontology_schema_url": "https://example.org/ontology.owl"
  }'
```

**Response (excerpt):**

```json
{
  "format_uri": "http://edamontology.org/format_4119",
  "label": "Shapefile",
  "comment": "Shapefile is a composite format including 3 mandatory files...",
  "parents": [
    "http://edamontology.org/format_2333",
    "http://edamontology.org/format_4126"
  ],
  "children": [],
  "equivalents": [],
  "file_extensions": ["dbf", "shp", "shx"],
  "media_type": "x-gis/x-shapefile (not in IANA)",
  "see_also": ["https://en.wikipedia.org/wiki/Shapefile"],
  "documentation": ["https://www.esri.com/..."]
}
```

The service fetches the ontology once, infers its namespace automatically, and caches the parsed graph for subsequent requests with the same `ontology_schema_url`.

## Development

### Prerequisites

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Installation

```shell
uv venv
uv sync
```

To also install development dependencies (testing, linting, type-checking):

```shell
uv sync --extra dev
```

### Running the Service

```shell
# Activate the virtual environment
source .venv/bin/activate

uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Interactive documentation (Swagger UI) is available at `http://localhost:8000/docs`.

### Testing

The project uses `pytest` for both unit and integration tests with the `fastapi::TestClient` for integration testing.

```shell
# Run all tests
pytest

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run with coverage report
pytest --cov=sos_file_format_service --cov-report=term-missing
```

## Project Structure

```
sos-file-format-service/
├── ontology/
│   └── edamontology_adapted.org.owl      # EO-extension of the EDAM ontology
├── mappings/
│   └── http---edamontology-org.json      # EDAM → validator format mappings
├── src/
│   ├── main.py                           # Uvicorn entry point
│   ├── config.py                         # Pydantic-settings configuration
│   ├── api/
│   │   ├── app.py                        # FastAPI app factory
│   │   ├── dependencies.py               # DI wiring (settings, services, translator)
│   │   ├── routers/                      # Endpoints
│   │   └── schemas/                      # DTOs
│   ├── service/                          # CompatibilityService & OntologyRegistry
│   ├── compatibility/
│   └── adapter/                          # Adapter classes for file format validator module
├── tests/
│   ├── unit/                             
│   └── integration/                 
├── pyproject.toml                        # Project metadata, dependencies, tool config
├── uv.lock                               # Locked dependency versions
└── README.md
```

## Deployment

### Configuration

All configuration is handled via environment variables prefixed with `SOS_FFS_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOS_FFS_MAPPINGS_DIR` | `mappings` | Directory containing (Ontology -> File Format) mapping files |
| `SOS_FFS_HOST` | `0.0.0.0` | Bind host |
| `SOS_FFS_PORT` | `8000` | Bind port |

### Containerisation (Docker)

The `Dockerfile` builds on [`logru/format-validator-deps`](https://hub.docker.com/r/logru/format-validator-deps), which bundles the GDAL/GEOS/PROJ toolchain `format-validator`'s dependencies need to compile (namely `fiona`, which has no prebuilt wheel for Python 3.14 yet), plus `uv` and the app itself:

```shell
docker build -t sos-file-format-service .
docker run -p 8000:8000 sos-file-format-service
```

#### docker compose

`docker-compose.yml` runs the API alongside an `nginx` container that serves the adapted EDAM ontology (`tests/fixtures/edamontology_adapted.org.owl`) over HTTP, so it can be used as an `ontology_schema_url` without leaving the Docker network:

```shell
docker compose up --build
```

- API: `http://localhost:8000`
- Ontology file: `http://localhost:8080/edamontology_adapted.org.owl` from the host, or `http://ontology/edamontology_adapted.org.owl` from the `api` container.

```bash
curl -X POST "http://localhost:8000/api/v1/format-info" \
  -H "Content-Type: application/json" \
  -d '{
    "format_identifier": "format_4119",
    "ontology_schema_url": "http://ontology/edamontology_adapted.org.owl"
  }'
```

### Runtime Requirements

- Any OWL/RDF ontology used by the `/compatibility` endpoint must be reachable via its `ontology_schema_url` (HTTP/HTTPS or local `file://` URIs).
- The mapping files in `mappings/` must be present for format translation to work.