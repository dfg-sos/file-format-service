# The service with the validator core, which defines no formats. Validator plugins are added at
# build time, see docs/integration.md:
#   docker build -t file-format-service .                                     # core only
#   docker build -t file-format-service-eo --build-arg EXTRAS=eo \
#     --build-arg BASE_IMAGE=ghcr.io/osgeo/gdal:ubuntu-small-3.13.3 .         # with the EO plugin
# EXTRAS: extras of pyproject.toml, space-separated, installed from uv.lock (locked versions).
# PLUGINS: further plugin requirements for `uv pip install`, space-separated (e.g. a wheel URL or
#   git+https://…#subdirectory=…); their dependencies are resolved at build time, not locked.
# BASE_IMAGE: the EO plugin needs the GDAL image: fiona has no cp314 wheel yet and is compiled
#   against the GDAL of the base image.
ARG BASE_IMAGE=python:3.14-slim

FROM ${BASE_IMAGE} AS build
ARG EXTRAS=""
ARG PLUGINS=""
# git: uv fetches format-validator (and Git plugins) from Git. Compilers, and the headers of a
# system Python (the GDAL image has one; python:*-slim ships them): for plugins built from source.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git \
    && if dpkg -s python3 >/dev/null 2>&1; then apt-get install -y --no-install-recommends python3-dev; fi \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /usr/local/bin/
# Build the venv on the base image's Python, which the runtime stage shares.
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=python3 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project $(for extra in ${EXTRAS}; do printf -- '--extra %s ' "$extra"; done)
# --no-sources: a plugin's development sources (e.g. a uv workspace) must not replace the
# format-validator installed above.
RUN if [ -n "${PLUGINS}" ]; then uv pip install --python /opt/venv/bin/python --no-sources ${PLUGINS}; fi

# Runtime: same base, without compilers and headers.
FROM ${BASE_IMAGE}
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /app
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
