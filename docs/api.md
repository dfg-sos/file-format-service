# API reference

Details of the endpoints listed in the [README](../README.md#api). Interactive documentation of all fields is served at `/docs` (Swagger UI).

The examples use the example ontology and mapping from `tests/fixtures/` (namespace `https://example.org/formats#`), with `https://example.org/formats.ttl` as a placeholder for the ontology's URL.

> **`ontology_namespace` vs `ontology_schema_url`:** the validation endpoints take the ontology's namespace (base URI), used to look up the [format mapping](integration.md#a-new-ontology-for-existing-validators). The ontology endpoints take the URL of the OWL/RDF file itself.

## Validation endpoints

There is one endpoint per validation mode. The deeper the mode, the more of the file the service needs:

| Endpoint | Checks | The service needs |
|----------|--------|-------------------|
| `POST /api/v1/validate/basic` | File extensions; for multi-file formats, the components present and in one directory | Only the paths |
| `POST /api/v1/validate/metadata` | Additionally, that the files exist and open as the format, and their [metadata](#metadata-checks) (e.g. CRS, declared geometry type). Only the header or declarations are read, so the cost does not grow with the file size | The files: uploaded, or on shared storage via `/validate/metadata/local` |
| `POST /api/v1/validate/content` | Additionally, every pixel, feature or record: truncated or corrupt data fails, and every geometry must match the expected geometry type. Runs only if the metadata checks did not fail; formats without a content reader yield `UNCERTAIN` | The files: uploaded, or on shared storage via `/validate/content/local` |

Each response holds a `status` (`SUCCESS`, `FAILURE` or `UNCERTAIN`) and the `errors`, `warnings` and `infos` of the validation. A format that is not mapped, or has no validator, yields `400`.

## `POST /api/v1/validate/basic`

Checks only the file names, so the client sends paths in a JSON body instead of the files. The service neither transfers nor reads the files. They need not be accessible to it, and no [shared directories](../README.md#configuration) are required.

```bash
curl -X POST "http://localhost:8000/api/v1/validate/basic" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/home/user/data/run42/roads.shp",
    "secondary_file_paths": [
      "/home/user/data/run42/roads.shx",
      "/home/user/data/run42/roads.dbf",
      "/home/user/data/run42/roads.prj"
    ],
    "ontology_namespace": "https://example.org/formats#",
    "format_identifier": "Shapefile"
  }'
```

## `POST /api/v1/validate/metadata` and `/validate/content`

Upload a file and validate it against a format:

```bash
curl -X POST "http://localhost:8000/api/v1/validate/metadata" \
  -F "file=@/path/to/your/file.geojson" \
  -F "ontology_namespace=https://example.org/formats#" \
  -F "format_identifier=GeoJSON" \
  -F 'expected_metadata={"crs": "EPSG:4326"}'
```

### Multi-file formats (e.g. Shapefile)

Upload the primary file as `file` and every remaining component as a repeated `secondary_files` part. Original file names must be preserved (components are matched by stem); names must be unique within a request.

```bash
curl -X POST "http://localhost:8000/api/v1/validate/metadata" \
  -F "file=@/path/to/roads.shp" \
  -F "secondary_files=@/path/to/roads.shx" \
  -F "secondary_files=@/path/to/roads.dbf" \
  -F "secondary_files=@/path/to/roads.prj" \
  -F "ontology_namespace=https://example.org/formats#" \
  -F "format_identifier=Shapefile"
```

### Metadata checks

The metadata and content endpoints take an optional `expected_metadata`: key/value pairs the file's metadata must match. In the upload it is a form field holding a JSON object; in the JSON body of the `/local` endpoints it is an object. The keys are not fixed by the service: the validator of the format decides which ones it supports. Currently:

| Formats | Keys |
|---------|------|
| Vector formats (e.g. GeoJSON, Shapefile, GeoPackage) | `crs`: any coordinate reference system string understood by `pyproj`, e.g. `EPSG:4326`<br>`geometry_type`: a GeoJSON-style geometry type such as `Point` or `MultiPolygon`, matched case-insensitively |
| Raster formats (e.g. GeoTIFF, COG) | `crs` |

- A key that is omitted (or empty) skips that check.
- A key the format's validator does not support yields `400`. For an abstract format such as `GISVector`, only the keys all its concrete formats support are accepted.
- A value that cannot be parsed (an unknown CRS or geometry type) yields `400`.
- `expected_metadata` that is not a JSON object of strings yields `422`.

## `POST /api/v1/validate/metadata/local` and `/validate/content/local`

When client and service run on the same host (or share a mounted volume), the client can send the file's path instead of uploading it. The service reads the file in place: nothing is transferred, copied or deleted. The result is the same as for the upload endpoint of the same mode. This is the intended mode for the format-aware CWL runner.

```bash
curl -X POST "http://localhost:8000/api/v1/validate/metadata/local" \
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
    "expected_metadata": {"crs": "EPSG:4326"}
  }'
```

The body takes the same fields as the upload, with `file_path` and `secondary_file_paths` (absolute paths, as the client sees them) instead of the files. The endpoints are disabled unless `SOS_FFS_SHARED_DIRS` is set (see [Configuration](../README.md#configuration)), and only files inside those directories are accepted, also after following symlinks.

| Status | When |
|--------|------|
| `200` | Validation ran; `status` holds the outcome |
| `400` | The format is not supported, `expected_metadata` has unsupported keys or values that cannot be parsed, or a path is not absolute |
| `403` | Local validation is disabled, or a path is outside the shared directories (including via `..` or symlinks) |
| `404` | A path inside a shared directory does not exist |

The request is checked before the paths, so a `400` comes before any `403` or `404`. Clients should fall back to the upload endpoint of the same mode on a `403`, e.g. for files outside the shared directories.

## Server-Timing header

The validation endpoints report how long the service's own steps took in a standard [`Server-Timing`](https://www.w3.org/TR/server-timing/) response header (milliseconds):

```
Server-Timing: validate;dur=0.4                        # /validate/basic
Server-Timing: receive;dur=1.8, validate;dur=812.3     # /validate/metadata, /validate/content
Server-Timing: resolve;dur=0.1, validate;dur=812.3     # /validate/metadata/local, /validate/content/local
```

`receive` covers writing the uploads to a temporary directory, `resolve` the path checks, and `validate` the validation itself. The multipart body is received and parsed before the endpoint runs, so `receive` does not include the network transfer: derive it as the client's round-trip time minus the reported durations.

## `POST /api/v1/compatibility`

Checks whether `actual_format` can be used where `expected_format` is required, following `rdfs:subClassOf` and `owl:equivalentClass`.

```bash
curl -X POST "http://localhost:8000/api/v1/compatibility" \
  -H "Content-Type: application/json" \
  -d '{
    "expected_format": "Vector",
    "actual_format": "Shapefile",
    "ontology_schema_url": "https://example.org/formats.ttl"
  }'
```

## `POST /api/v1/format-info`

```bash
curl -X POST "http://localhost:8000/api/v1/format-info" \
  -H "Content-Type: application/json" \
  -d '{
    "format_identifier": "Shapefile",
    "ontology_schema_url": "https://example.org/formats.ttl"
  }'
```

Formats can be given as short name (`Shapefile`) or full IRI (`https://example.org/formats#Shapefile`); the namespace is inferred from the ontology. Response (excerpt):

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

## Errors of the ontology endpoints

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

The service fetches each ontology once, infers its namespace, and caches the parsed graph for later requests with the same `ontology_schema_url`.
