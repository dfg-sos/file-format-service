ARG GDAL_IMAGE=ghcr.io/osgeo/gdal:ubuntu-small-3.13.3

FROM ${GDAL_IMAGE} AS build
# format-validator pulls in geospatial deps (fiona, rasterio, shapely, pyproj,netcdf4).
# Most ship manylinux wheels for cp314, but fiona does not yet, so
# it is compiled from source against the GDAL of the base image. git is
# needed for uv to fetch the format-validator Git dependency.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        git \          
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /usr/local/bin/
# Build the venv on the system Python, which the runtime stage shares.
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/bin/python3 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Runtime: same GDAL base, without compilers and headers.
FROM ${GDAL_IMAGE}
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /app
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
