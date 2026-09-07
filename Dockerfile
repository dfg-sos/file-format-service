FROM logru/format-validator-deps:latest

# format-validator pulls in geospatial deps (fiona, rasterio, shapely, pyproj,
# netcdf4). Most ship manylinux wheels for cp314, but fiona does not yet, so
# it is compiled from source; the base image already carries GDAL/GEOS/PROJ
# and their headers plus a matching build toolchain. Only git is missing,
# needed for uv to fetch the format-validator Git dependency.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /uvx /usr/local/bin/

WORKDIR /app

# Resolve dependencies in their own layer so it's only redone when the
# lockfile changes, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY mappings/ mappings/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
