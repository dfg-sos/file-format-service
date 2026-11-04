# SOS File Format Service

A FastAPI service that validates files against formats defined in an OWL/RDF ontology, and checks whether two formats are compatible according to that ontology (`rdfs:subClassOf`, `owl:equivalentClass`). Validation is done by the [`format_validator`](https://github.com/dfg-sos/file-format-validator) module, whose core defines no formats: validator plugins add them, e.g. the EO plugin `format-validator-eo` (GeoTIFF, Shapefile, GeoPackage, …). The service ships no ontology of its own, see [Ontologies and mappings](#ontologies-and-mappings).

## Quick start

Requires Python >= 3.14 and [uv](https://docs.astral.sh/uv/).

```shell
uv sync --extra dev                # or --extra eo: the EO plugin without the development tools
mkdir -p mappings && cp tests/fixtures/mappings/example-formats.json mappings/   # example mapping
uv run uvicorn main:app --app-dir src --port 8000
```

Swagger UI is served at `http://localhost:8000/docs`.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check probe |
| `POST` | `/api/v1/validate/basic` | Check file names against a format; only the paths are sent |
| `POST` | `/api/v1/validate/metadata` | Open uploaded files as the format and check their header and metadata |
| `POST` | `/api/v1/validate/metadata/local` | Same, for files on storage shared with the service, without uploading them |
| `POST` | `/api/v1/validate/content` | Additionally read every pixel, feature or record of uploaded files |
| `POST` | `/api/v1/validate/content/local` | Same, for files on storage shared with the service, without uploading them |
| `POST` | `/api/v1/compatibility` | Check compatibility between two formats |
| `POST` | `/api/v1/format-info` | Retrieve metadata of a format from an ontology |

The examples use the [example ontology and mapping](#ontologies-and-mappings), with `https://example.org/formats.ttl` as a placeholder for the ontology's URL. Multi-file formats, local validation, metadata checks, responses and errors are described in the [API reference](docs/api.md).

```bash
# Check a file name, without sending the file
curl -X POST "http://localhost:8000/api/v1/validate/basic" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/your/file.geojson", "ontology_namespace": "https://example.org/formats#", "format_identifier": "GeoJSON"}'

# Upload a file and validate its header, including its CRS
curl -X POST "http://localhost:8000/api/v1/validate/metadata" \
  -F "file=@/path/to/your/file.geojson" \
  -F "ontology_namespace=https://example.org/formats#" \
  -F "format_identifier=GeoJSON" \
  -F 'expected_metadata={"crs": "EPSG:4326"}'

# Is a Shapefile usable where a Vector format is expected?
curl -X POST "http://localhost:8000/api/v1/compatibility" \
  -H "Content-Type: application/json" \
  -d '{"expected_format": "Vector", "actual_format": "Shapefile", "ontology_schema_url": "https://example.org/formats.ttl"}'

# Label, comment, parents, children and annotations of a format
curl -X POST "http://localhost:8000/api/v1/format-info" \
  -H "Content-Type: application/json" \
  -d '{"format_identifier": "Shapefile", "ontology_schema_url": "https://example.org/formats.ttl"}'
```

## Ontologies and mappings

The service is not tied to a particular ontology:

- **`/compatibility` and `/format-info`** load the ontology from the `ontology_schema_url` of the request (HTTP(S) or `file://`) and cache it. Accepted serialisations are RDF/XML (`.owl`, `.rdf`), Turtle (`.ttl`), N-Triples (`.nt`), N3 (`.n3`) and JSON-LD (`.jsonld`), detected from the file extension, and over HTTP(S) first from the `Content-Type`.
- **The `/validate/...` endpoints** translate the `format_identifier` of the ontology given by `ontology_namespace` into a format of the validator. This requires a mapping file for that namespace in `mappings/` (`/app/mappings` in the image). No mappings are shipped.

[Integrating ontologies and validators](docs/integration.md) describes mapping files, and how to add validators for new formats as plugins without changing the service.

The SOS vocabularies, including the EO file formats ontology, are maintained in [dfg-sos/ontologies](https://github.com/dfg-sos/ontologies) and published at `https://dfg-sos.github.io/ontologies/eo-formats.owl` (namespace `https://dfg-sos.github.io/ontologies/eo-formats#`).

For tests and documentation, `tests/fixtures/ontologies/example-formats.ttl` is a small example ontology (namespace `https://example.org/formats#`), and `tests/fixtures/mappings/example-formats.json` its mapping. To use it with a local service, reference it as `file:///<path to repo>/tests/fixtures/ontologies/example-formats.ttl`.

## Deployment

### Configuration

Environment variables, prefixed with `SOS_FFS_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOS_FFS_HOST` | `0.0.0.0` | Bind host |
| `SOS_FFS_PORT` | `8000` | Bind port |
| `SOS_FFS_SHARED_DIRS` | *(empty)* | Directories in which clients may reference files for `/validate/metadata/local` and `/validate/content/local`; empty disables these endpoints. Comma-separated absolute paths, `host_path` or `host_path:container_path` when the service sees the directory elsewhere (paths containing `:` or `,` are not supported). |

```bash
SOS_FFS_SHARED_DIRS=/home/user/data,/scratch      # service runs directly on the host
SOS_FFS_SHARED_DIRS=/home/user/data:/data         # container with /home/user/data mounted at /data
```

Clients always send host paths; the service maps them to the container path.

### Concurrency

Validation runs in a thread pool, so a long validation does not hold up other requests. For CPU-heavy content validation, set `WEB_CONCURRENCY` to run several worker processes (each keeps its own caches of mappings and ontologies). The service keeps no state between requests, so it can also run as several replicas behind a load balancer.

### Container image

Two images are published (`linux/amd64`) as `latest` and, for Git tags `v1.2.3`, as `1.2.3` and `1.2`:

| Image | Validators |
|-------|------------|
| `ghcr.io/dfg-sos/file-format-service` | none: the core, for images with other plugins |
| `ghcr.io/dfg-sos/file-format-service-eo` | the EO plugin (on the GDAL base image) |

Without a plugin, validation rejects every format; the compatibility and format-info endpoints work with any image. Other plugins are added with the Dockerfile's build arguments or in a derived image, see [Installing a plugin](docs/integration.md#installing-a-plugin). At startup the service logs the formats of the installed plugins. Mappings, shared data and local ontologies are mounted at run time:

```shell
docker run -p 8000:8000 \
  -v /home/user/my-mappings:/app/mappings:ro \
  -v /home/user/data:/data:ro \
  -e SOS_FFS_SHARED_DIRS=/home/user/data:/data \
  -v /home/user/ontology:/ontology:ro \
  ghcr.io/dfg-sos/file-format-service-eo:latest
```

Local ontologies are then referenced as `file:///ontology/<file>.owl`. `docker-compose.yml` runs the same image with these mounts as commented examples (`docker compose up -d`).

## Development

The tests use the EO plugin, which the extra `dev` includes.

```shell
uv run pytest                      # all tests
uv run pytest tests/unit           # unit tests only (tests/integration for the API tests)
uv run pytest --cov=src            # with coverage
uv run ruff check src tests
```

The code in `src/` is layered: `api/` (FastAPI routers, schemas, dependency wiring), `service/` (compatibility checks, ontology fetching and caching) and `core/` (ontology parsing and reasoning with `rdflib`).
