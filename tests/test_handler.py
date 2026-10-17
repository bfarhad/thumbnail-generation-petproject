"""Unit tests for the Azure Function thumbnail handler.

Mirrors the structure of the AWS Lambda test suite. Azure SDK calls are patched
so no real storage account is needed.
"""

import io
import json
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Point imports at src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Set required env vars before importing the module
os.environ.setdefault("STORAGE_ACCOUNT_NAME", "teststorage")
os.environ.setdefault("STORAGE_ACCOUNT_KEY",  "dGVzdGtleQ==")  # base64 "testkey"
os.environ.setdefault("BLOB_CONTAINER",        "images")
os.environ.setdefault("THUMBNAIL_SIZE",        "64")
os.environ.setdefault("SAS_EXPIRY_HOURS",      "1")

import function_app as handler  # noqa: E402
import azure.functions as func  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def image_bytes(fmt: str = "PNG", size: tuple = (400, 200), mode: str = "RGB") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, "red").save(out, format=fmt)
    return out.getvalue()


def make_request(
    data: bytes,
    content_type: str = "image/png",
) -> func.HttpRequest:
    return func.HttpRequest(
        method="POST",
        url="https://example.azurewebsites.net/api/thumbnails",
        headers={"Content-Type": content_type},
        params={},
        route_params={},
        body=data,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_azure(monkeypatch):
    """Patch BlobServiceClient and generate_blob_sas so nothing hits Azure."""
    uploaded: dict = {}

    mock_container = MagicMock()

    def fake_upload(name, data, overwrite=True, content_type=None):
        uploaded[name] = (data if isinstance(data, bytes) else data.read(), content_type)

    mock_container.upload_blob.side_effect = fake_upload

    mock_service = MagicMock()
    mock_service.get_container_client.return_value = mock_container

    monkeypatch.setattr(handler, "_blob_service", mock_service)
    monkeypatch.setattr(
        "function_app.generate_blob_sas",
        lambda **kw: "sv=2024&sig=fake",
    )
    return uploaded


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_png_creates_thumbnail_and_stores_both_blobs(patch_azure):
    resp = handler.thumbnails(make_request(image_bytes()))
    body = json.loads(resp.get_body())
    assert resp.status_code == 200
    assert body["width"] == 64
    assert body["height"] == 32  # aspect ratio preserved
    assert body["original_key"].startswith("originals/")
    assert body["thumbnail_key"].startswith("thumbnails/")
    assert body["thumbnail_url"].startswith("https://teststorage.blob.core.windows.net/")
    assert body["original_key"] in patch_azure
    assert body["thumbnail_key"] in patch_azure
    _, thumb_ct = patch_azure[body["thumbnail_key"]]
    assert thumb_ct == "image/jpeg"


@pytest.mark.parametrize("fmt,ct", [
    ("JPEG", "image/jpeg"),
    ("WEBP", "image/webp"),
])
def test_other_formats(fmt, ct):
    resp = handler.thumbnails(make_request(image_bytes(fmt), ct))
    assert resp.status_code == 200


def test_rgba_png_is_flattened():
    resp = handler.thumbnails(make_request(image_bytes(mode="RGBA")))
    assert resp.status_code == 200


def test_unsupported_type():
    resp = handler.thumbnails(make_request(b"x", "image/gif"))
    assert resp.status_code == 415


def test_empty_body():
    resp = handler.thumbnails(make_request(b""))
    assert resp.status_code == 400


def test_not_an_image():
    resp = handler.thumbnails(make_request(b"definitely not an image"))
    assert resp.status_code == 400


def test_too_large(monkeypatch):
    monkeypatch.setattr(handler, "MAX_BYTES", 10)
    resp = handler.thumbnails(make_request(image_bytes()))
    assert resp.status_code == 413


def test_response_json_schema():
    resp = handler.thumbnails(make_request(image_bytes()))
    body = json.loads(resp.get_body())
    assert all(k in body for k in ("id", "thumbnail_url", "original_key", "thumbnail_key", "width", "height"))
    assert len(body["id"]) == 32  # uuid4().hex
