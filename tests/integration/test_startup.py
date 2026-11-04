"""Integration tests for the application startup: plugins and mappings."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_format_translator, load_format_translator

from ..conftest import MAPPINGS


def _client(mappings_dir: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_format_translator] = lambda: load_format_translator(mappings_dir)
    return TestClient(app)


class TestStartup:
    def test_logs_formats_of_installed_plugins(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="api.app"), _client(MAPPINGS) as client:
            assert client.get("/health").status_code == 200
        assert "Formats with a validator:" in caplog.text
        assert "'GeoTIFF'" in caplog.text

    def test_mapping_to_format_without_plugin_stops_startup(self, tmp_path: Path) -> None:
        mapping = {"ontology_uri": "https://a.org/fmt#", "mappings": {"Reads": "FASTQ"}}
        (tmp_path / "a.json").write_text(json.dumps(mapping))
        with pytest.raises(ValueError, match=r"a\.json: .*FASTQ"):
            with _client(tmp_path):
                pass
