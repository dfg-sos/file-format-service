# Integrating ontologies and validators

How to use the service with another ontology, or with formats it cannot validate yet. Neither requires changing the service.

The ontology endpoints and the validation endpoints use an ontology differently:

- **`/compatibility` and `/format-info`** load the ontology from the `ontology_schema_url` of the request and reason over it directly. Any ontology works without further setup.
- **The `/validate/...` endpoints** translate `ontology_namespace` + `format_identifier` into a format identifier of the [`format_validator`](https://github.com/dfg-sos/file-format-validator), whose validator then checks the file. This translation is a *mapping file*, one per ontology.

So there are two ways to integrate:

| You have | You add |
|----------|---------|
| [An ontology whose formats existing validators cover](#a-new-ontology-for-existing-validators) | A mapping file |
| [Formats no validator covers yet](#new-validators-as-plugins) | A validator plugin and a mapping file |

## A new ontology for existing validators

A mapping file maps the format identifiers of one ontology to those of the validator:

```json
{
  "ontology_uri": "https://example.org/formats#",
  "mappings": { "Shapefile": "shapefile", "GeoTIFF": "geotiff", "Vector": "gisvector" }
}
```

- `ontology_uri` is the ontology's namespace, as clients send it in `ontology_namespace`. A format's full IRI is `ontology_uri` followed by its identifier.
- The validator's identifiers are listed by `format_validator.supported_formats()` (built-in ones and those of installed [plugins](#new-validators-as-plugins)) and matched case-insensitively. Abstract ones such as `gisvector` or `gisraster` accept a file that is valid for any of their concrete formats.
- Several ontologies can map to the same validators, e.g. both the SOS EO formats ontology and EDAM can map to `geotiff`.

The service loads every `*.json` file in `mappings/` (git-ignored; `/app/mappings` in the image, mounted at run time) on the first validation request. No mappings are shipped: without any, validation rejects every format and the service logs a warning. Loading fails if a file maps to an identifier the validator does not know, or two files map the same format to different identifiers.

For an example, see `tests/fixtures/ontologies/example-formats.ttl` and its mapping `tests/fixtures/mappings/example-formats.json`.

## New validators as plugins

Validators for formats the validator does not cover, e.g. of another domain, ship as separate Python packages. The service loads all installed plugins at startup, before the mappings, so mappings can refer to the plugins' identifiers.

### Writing a plugin

A plugin registers its validators with `@registry.register(...)`:

```python
# format_validator_bio/validators.py
from format_validator.model import FileFormatValidator, FormatIdentifier, ValidationResult
from format_validator.registry import registry


@registry.register(FormatIdentifier("fasta"))
class FastaValidator(FileFormatValidator):
    def get_extensions(self):
        return [".fasta", ".fa"]

    def assert_can_open(self, request):  # metadata mode: read the header only
        ...
        return ValidationResult.success(request)

    def assert_content(self, request):  # content mode: read every record; optional, UNCERTAIN otherwise
        ...
        return ValidationResult.success(request)
```

and declares the module under the entry-point group `format_validator.validators` in its `pyproject.toml`:

```toml
[project.entry-points."format_validator.validators"]
bio = "format_validator_bio.validators"
```

See [Validator Plugins](https://github.com/dfg-sos/file-format-validator#validator-plugins) in the validator's README for details.

### Installing a plugin

For the container image, extend it. The image has no `pip`, so install with `uv`:

```dockerfile
FROM ghcr.io/dfg-sos/file-format-service:<version>
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /usr/local/bin/
RUN uv pip install --python /opt/venv/bin/python format-validator-bio
```

The image has neither `git` nor a compiler, so install plugins from a wheel or an index, or add the build tools in the derived image. When running the service from source, install the plugin into its environment (`uv pip install ...`).

### Mapping the plugin's formats

Like the built-in validators, a plugin's validators are only reachable through a mapping file, e.g. from EDAM:

```json
{
  "ontology_uri": "http://edamontology.org/",
  "mappings": { "format_1929": "fasta" }
}
```

A client then validates with `"ontology_namespace": "http://edamontology.org/"` and `"format_identifier": "format_1929"`.

### Behaviour

- A plugin that fails to import is logged and skipped; mappings to its identifiers then fail to load.
- A plugin that registers an identifier that is already taken stops the service at startup.
- Plugins run in the service process as trusted code.
