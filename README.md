# SOS File Format Service

A FastAPI REST API service for validating Earth Observation (EO) file formats and checking ontology-based format compatibility.

The service bridges ontology-specific format identifiers (e.g. from the [SOS EO formats ontology](https://github.com/dfg-sos/ontologies)) with an external `format_validator` module, enabling automated validation of uploaded geospatial files. Furthermore static compatibility checks can be executed upon existing OWL/RDF ontologies. The service ships no ontology of its own, see [Ontologies and mappings](#ontologies-and-mappings).

## Features

- **File Format Validation** — Upload a file and validate it against a required format using multiple validation modes (`basic`, `structural`, `full`). `full` mode also validates file metadata against optional expected values.
- **Dynamic Ontology-based Compatibility Checks** — Check whether one format is compatible with another by evaluating `rdfs:subClassOf` and `owl:equivalentClass` relationships in any user-supplied OWL/RDF ontology.
- **Remote Ontology Support** — Ontologies are fetched on demand from a provided schema URL and cached in memory for subsequent requests.

## Architecture Overview

The service follows a layered architecture:

- **API Layer** (`api/`) — FastAPI routers, Pydantic request/response schemas, and exception handlers.
- **Service Layer** (`service/`) — Business logic, including `CompatibilityService` for ontology queries and `OntologyRegistry` for fetching and caching remote ontologies.
- **Adapter Layer** (`adapter/`) — Bridges between HTTP API types and the external `format_validator` module (`HTTPValidationRequestBuilder`, `HTTPValidationResponseHandler`).
- **Core Layer** (`core/`) — OWL/RDF ontology parsing and reasoning using `rdflib` (`FormatOntology`, `CompatibilityResult`).
- **Configuration** (`config.py`) — Pydantic-settings based configuration with environment variable support.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check probe |
| `POST` | `/api/v1/validate` | Validate an uploaded file against a required format |
| `POST` | `/api/v1/validate/local` | Validate a file on storage shared with the service, without uploading it |
| `POST` | `/api/v1/compatibility` | Check compatibility between two format identifiers |
| `POST` | `/api/v1/format-info` | Retrieve detailed metadata for a format from an ontology |

The examples below use the [example ontology and mapping](#example-ontology-and-mapping) from `tests/fixtures/`, with `https://example.org/formats.ttl` as a placeholder for the ontology's URL.

### Example: Validate a File

```bash
curl -X POST "http://localhost:8000/api/v1/validate" \
  -F "file=@/path/to/your/file.geojson" \
  -F "ontology_namespace=https://example.org/formats#" \
  -F "format_identifier=GeoJSON" \
  -F "mode=full"
```

#### Multi-file formats (e.g. Shapefile)

Upload the primary file as `file` and every remaining component as a repeated `secondary_files` part. Original file names must be preserved (components are matched by stem); names must be unique within a request.

```bash
curl -X POST "http://localhost:8000/api/v1/validate" \
  -F "file=@/path/to/roads.shp" \
  -F "secondary_files=@/path/to/roads.shx" \
  -F "secondary_files=@/path/to/roads.dbf" \
  -F "secondary_files=@/path/to/roads.prj" \
  -F "ontology_namespace=https://example.org/formats#" \
  -F "format_identifier=Shapefile" \
  -F "mode=structural"
```

> **Note:** The validation endpoint expects `ontology_namespace` (the ontology's base URI, used for format mapping lookup), while the compatibility endpoint expects `ontology_schema_url` (the URL to the actual OWL/RDF schema file).

In `full` mode, additional optional fields let you validate a file's metadata against an expected value. For EO these include: `expected_crs` (any coordinate reference system string understood by `pyproj`, e.g. `EPSG:4326`) and `expected_geometry_type` (a GeoJSON-style geometry type such as `Point` or `MultiPolygon`, matched case-insensitively; only applies to vector formats). Omitting either field skips that check. A value that cannot be parsed (an unknown CRS or geometry type) yields an `UNCERTAIN` result.

### Example: Validate a File on Shared Storage

When client and service run on the same host (or share a mounted volume), the client can send the file's path instead of uploading it. The service reads the file in place: nothing is transferred, copied or deleted. The result is the same as for `/validate`. This is the intended mode for the format-aware CWL runner.

```bash
curl -X POST "http://localhost:8000/api/v1/validate/local" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/home/user/data/run42/roads.shp",
    "secondary_file_paths": [
      "/home/user/data/run42/roads.shx",
      "/home/user/data/run42/roads.dbf",
      "/home/user/data/run42/roads.prj"
    ],
    "ontology_namespace": "https://example.org/formats#",
    "format_identifier": "Shapefile",
    "mode": "full",
    "expected_crs": "EPSG:4326"
  }'
```

The body takes the same fields as `/validate`, with `file_path` and `secondary_file_paths` (absolute paths, as the client sees them) instead of the uploads. The endpoint is disabled unless `SOS_FFS_SHARED_DIRS` is set (see [Configuration](#configuration)), and only files inside those directories are accepted, also after following symlinks.

| Status | When |
|--------|------|
| `200` | Validation ran; `status` holds the outcome |
| `400` | A path is not absolute, the mode is invalid, or the format is not supported |
| `403` | Local validation is disabled, or a path is outside the shared directories (including via `..` or symlinks) |
| `404` | A path inside a shared directory does not exist |

Clients should fall back to uploading via `/validate` on a `403`, e.g. for files outside the shared directories.

### Server-Timing header

Both validation endpoints report how long the service's own steps took in a standard [`Server-Timing`](https://www.w3.org/TR/server-timing/) response header (milliseconds):

```
Server-Timing: receive;dur=1.8, validate;dur=812.3     # /validate
Server-Timing: resolve;dur=0.1, validate;dur=812.3     # /validate/local
```

`receive` covers writing the uploads to a temporary directory, `resolve` the path checks, and `validate` the validation itself. The multipart body is received and parsed before the endpoint runs, so `receive` does not include the network transfer: derive it as the client's round-trip time minus the reported durations.

### Example: Check Compatibility

```bash
curl -X POST "http://localhost:8000/api/v1/compatibility" \
  -H "Content-Type: application/json" \
  -d '{
    "expected_format": "Vector",
    "actual_format": "Shapefile",
    "ontology_schema_url": "https://example.org/formats.ttl"
  }'
```

### Example: Format Info
```bash
curl -X POST "http://localhost:8000/api/v1/format-info" \
  -H "Content-Type: application/json" \
  -d '{
    "format_identifier": "https://example.org/formats#Shapefile",
    "ontology_schema_url": "https://example.org/formats.ttl"
  }'
```

The user can omit the ontologies namespace since it is already available in the `owl` schema:
```bash
curl -X POST "http://localhost:8000/api/v1/format-info" \
  -H "Content-Type: application/json" \
  -d '{
    "format_identifier": "Shapefile",
    "ontology_schema_url": "https://example.org/formats.ttl"
  }'
```

**Response (excerpt):**

```json
{
  "format_uri": "https://example.org/formats#Shapefile",
  "label": "Shapefile",
  "comment": "Shapefile is a composite format including 3 mandatory files (.shp, .shx, .dbf).",
  "parents": ["https://example.org/formats#Vector"],
  "children": [],
  "equivalents": [],
  "see_also": ["https://en.wikipedia.org/wiki/Shapefile"],
  "annotations": {
    "http://www.w3.org/2000/01/rdf-schema#label": ["Shapefile"],
    "https://example.org/formats#fileExtension": ["dbf", "shp", "shx"],
    "https://example.org/formats#mediaType": ["x-gis/x-shapefile"],
    "...": []
  }
}
```

`label`, `comment`, `see_also`, `parents`, `children` and `equivalents` come from standard RDFS/OWL predicates and work with any ontology. `annotations` lists every annotation of the class under its predicate IRI, whatever the ontology calls it (e.g. file extensions or media types).

### Unknown formats

Both ontology endpoints first check that every requested format is declared as a class in the ontology (`rdf:type owl:Class`). An unknown format is reported as an error instead of a `compatible: false` or an empty metadata response:

| Endpoint | Status | When |
|----------|--------|------|
| `/api/v1/compatibility` | `422` | `expected_format` and/or `actual_format` is not defined |
| `/api/v1/format-info` | `404` | `format_identifier` is not defined |

The error body lists exactly the unknown formats as expanded IRIs, so you can see which namespace was assumed:

```json
{
  "detail": {
    "message": "Format(s) not defined in ontology https://example.org/formats.ttl",
    "unknown_formats": [
      "https://example.org/formats/format_99998",
      "https://example.org/formats/format_99999"
    ]
  }
}
```

`/compatibility` returns `200` with `compatible: false` only when both formats are defined but unrelated. Both endpoints also return `400` for an ontology schema that cannot be parsed, `404` for a local (`file://`) schema that does not exist, `502` for one that cannot be fetched, and `422` for an invalid request body.

The service fetches the ontology once, infers its namespace automatically, and caches the parsed graph for subsequent requests with the same `ontology_schema_url`.

## Ontologies and mappings

The service is not tied to a particular ontology. The two kinds of endpoints need different inputs:

- `/compatibility` and `/format-info` load the ontology from the `ontology_schema_url` of the request. Nothing has to be configured. Accepted serialisations are RDF/XML (`.owl`, `.rdf`), Turtle (`.ttl`), N-Triples (`.nt`), N3 (`.n3`) and JSON-LD (`.jsonld`). The format is taken from the file extension, and for HTTP(S) URLs first from the `Content-Type` of the response.
- `/validate` and `/validate/local` translate the `format_identifier` of the ontology given by `ontology_namespace` into a format of the validator. This requires a [mapping file](#format-mappings) for that namespace.

The SOS vocabularies, including the EO file formats ontology, are maintained in [dfg-sos/ontologies](https://github.com/dfg-sos/ontologies) and published at `https://dfg-sos.github.io/ontologies/eo-formats.owl` (namespace `https://dfg-sos.github.io/ontologies/eo-formats#`). Pass that URL as `ontology_schema_url`, and provide a mapping for its namespace to validate files against its formats.

### Example ontology and mapping

`tests/fixtures/ontologies/example-formats.ttl` is a small format ontology in the namespace `https://example.org/formats#` (`Raster` > `GeoTIFF` > `COG`, `Vector` > `Shapefile`, `GeoJSON`, …). `tests/fixtures/mappings/example-formats.json` maps its formats to the validator's. The tests and the examples in this README use them. Format identifiers can be given as short name (`Shapefile`) or full IRI (`https://example.org/formats#Shapefile`).

To try the examples against a local service, copy the mapping into `mappings/` and use a `file://` URL for the ontology:

```shell
mkdir -p mappings && cp tests/fixtures/mappings/example-formats.json mappings/
# "ontology_schema_url": "file:///<path to repo>/tests/fixtures/ontologies/example-formats.ttl"
```

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
├── mappings/                             # Format mappings (git-ignored, mount point in the image)
├── src/
│   ├── main.py                           # Uvicorn entry point
│   ├── config.py                         # Pydantic-settings configuration
│   ├── core/                             # FormatOntology & CompatibilityResult
│   ├── api/
│   │   ├── app.py                        # FastAPI app factory
│   │   ├── dependencies.py               # DI wiring (settings, services, translator)
│   │   ├── routers/                      # Endpoints (validation, compatibility, format_info)
│   │   └── schemas/                      # DTOs
│   ├── service/                          # CompatibilityService & OntologyRegistry
│   └── adapter/                          # Adapter classes for file format validator module
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       ├── ontologies/                   # Example ontology (+ edge cases for unit tests)
│       ├── mappings/                     # Example mapping for it
│       └── data/                         # Sample files to validate
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml                        # Project metadata, dependencies, tool config
├── uv.lock                               # Locked dependency versions
└── README.md
```

## Deployment

### Configuration

All configuration is handled via environment variables prefixed with `SOS_FFS_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOS_FFS_HOST` | `0.0.0.0` | Bind host |
| `SOS_FFS_PORT` | `8000` | Bind port |
| `SOS_FFS_SHARED_DIRS` | *(empty)* | Directories shared with clients, enabling `/validate/local`. Comma-separated entries of `host_path` or `host_path:container_path` (see below). Empty disables the endpoint. |

`SOS_FFS_SHARED_DIRS` lists the directories in which clients may reference files, as absolute paths. Each entry is `host_path` when the service sees the directory under the same path as the client, or `host_path:container_path` when it is mounted elsewhere, e.g. inside a container. Clients always send host paths; the service maps them to the container path. Paths containing `:` or `,` are not supported.

```bash
# Service runs directly on the host
SOS_FFS_SHARED_DIRS=/home/user/data,/scratch

# Service runs in a container with /home/user/data mounted at /data
SOS_FFS_SHARED_DIRS=/home/user/data:/data
```

### Format mappings

A mapping file translates the format identifiers of one ontology (`ontology_uri`, its namespace) to the format identifiers of the validator. The service loads every `*.json` file in `mappings/` (`/app/mappings` in the image, git-ignored) at startup. No mappings are shipped: without any, validation rejects every format, and the service logs a warning at startup.

```json
{
  "ontology_uri": "https://example.org/formats#",
  "mappings": { "Shapefile": "shapefile", "GeoTIFF": "geotiff" }
}
```

See `tests/fixtures/mappings/example-formats.json` for a complete file.

### Container image

The image is published to `ghcr.io/dfg-sos/file-format-service` (`linux/amd64`) as `latest` and, for Git tags `v1.2.3`, as `1.2.3` and `1.2`. Mappings, shared data and local ontologies are mounted at run time:

```shell
docker run -p 8000:8000 \
  -v /home/user/my-mappings:/app/mappings:ro \
  -v /home/user/data:/data:ro \
  -e SOS_FFS_SHARED_DIRS=/home/user/data:/data \
  -v /home/user/ontology:/ontology:ro \
  ghcr.io/dfg-sos/file-format-service:latest
```

Local ontologies are then referenced as `file:///ontology/<file>.owl`. `docker-compose.yml` runs the same image with these mounts as commented examples:

```shell
docker compose up -d
```

### Runtime Requirements

- Any OWL/RDF ontology used by the `/compatibility` endpoint must be reachable via its `ontology_schema_url` (HTTP/HTTPS or local `file://` URIs).
- A mapping file for each ontology namespace used with the validation endpoints must be present in, or mounted to, `mappings/`.