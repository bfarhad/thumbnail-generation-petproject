"""POST /api/thumbnails — store an uploaded image and return a SAS thumbnail URL.

Request:  raw image bytes (image/jpeg | image/png | image/webp),
          Azure Function key in ?code= query param (AuthLevel.FUNCTION).
Response: 200 {"id", "thumbnail_url", "original_key", "thumbnail_key", "width", "height"}

Azure equivalent of the AWS Lambda thumbnail service:
  Lambda         → Azure Functions v2 (Python 3.11, consumption plan)
  S3             → Azure Blob Storage (private container)
  Presigned URL  → SAS URL
  API Gateway    → Azure Function HTTP trigger (AuthLevel.FUNCTION key)
"""

import io
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import azure.functions as func
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    generate_blob_sas,
)
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
STORAGE_ACCOUNT_NAME = os.environ["STORAGE_ACCOUNT_NAME"]
STORAGE_ACCOUNT_KEY  = os.environ["STORAGE_ACCOUNT_KEY"]
CONTAINER_NAME       = os.environ["BLOB_CONTAINER"]
THUMBNAIL_SIZE       = int(os.getenv("THUMBNAIL_SIZE", "256"))
SAS_EXPIRY_HOURS     = int(os.getenv("SAS_EXPIRY_HOURS", "24"))

ALLOWED_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_BYTES = 4 * 1024 * 1024

# ---------------------------------------------------------------------------
# Lazy singleton blob client
# ---------------------------------------------------------------------------
_blob_service: BlobServiceClient | None = None


def _client() -> BlobServiceClient:
    global _blob_service
    if _blob_service is None:
        _blob_service = BlobServiceClient(
            account_url=f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=STORAGE_ACCOUNT_KEY,
        )
    return _blob_service


# ---------------------------------------------------------------------------
# Azure Functions v2 app — decorator-based (requires AzureWebJobsFeatureFlags=EnableWorkerIndexing)
# ---------------------------------------------------------------------------
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _json(status: int, body: dict) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body),
        status_code=status,
        mimetype="application/json",
    )


def make_thumbnail(data: bytes, size: int) -> tuple[bytes, tuple[int, int]]:
    """Return JPEG bytes of the image scaled to fit in size×size, and its dimensions."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((size, size), Image.LANCZOS)
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.getchannel("A"))
            img = flat
        else:
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue(), img.size


@app.route(route="thumbnails", methods=["POST"])
def thumbnails(req: func.HttpRequest) -> func.HttpResponse:
    # ── Content-Type validation ──────────────────────────────────────────────
    content_type = req.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        return _json(415, {"error": f"Unsupported Content-Type; use one of {sorted(ALLOWED_TYPES)}"})

    # ── Body ─────────────────────────────────────────────────────────────────
    data = req.get_body()
    if not data:
        return _json(400, {"error": "Empty body"})
    if len(data) > MAX_BYTES:
        return _json(413, {"error": f"Image too large (max {MAX_BYTES} bytes)"})

    # ── Thumbnail generation ─────────────────────────────────────────────────
    try:
        thumb, (width, height) = make_thumbnail(data, THUMBNAIL_SIZE)
    except Exception:
        return _json(400, {"error": "Body is not a valid image"})

    # ── Upload to Blob Storage ───────────────────────────────────────────────
    image_id    = uuid.uuid4().hex
    ext         = ALLOWED_TYPES[content_type]
    original_key  = f"originals/{image_id}.{ext}"
    thumbnail_key = f"thumbnails/{image_id}.jpg"

    client = _client()
    container = client.get_container_client(CONTAINER_NAME)

    container.upload_blob(name=original_key,  data=data,  overwrite=True,
                          content_type=content_type)
    container.upload_blob(name=thumbnail_key, data=thumb, overwrite=True,
                          content_type="image/jpeg")

    # ── Generate SAS URL ─────────────────────────────────────────────────────
    sas_token = generate_blob_sas(
        account_name=STORAGE_ACCOUNT_NAME,
        container_name=CONTAINER_NAME,
        blob_name=thumbnail_key,
        account_key=STORAGE_ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=SAS_EXPIRY_HOURS),
    )
    thumbnail_url = (
        f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
        f"/{CONTAINER_NAME}/{thumbnail_key}?{sas_token}"
    )

    return _json(200, {
        "id":            image_id,
        "thumbnail_url": thumbnail_url,
        "original_key":  original_key,
        "thumbnail_key": thumbnail_key,
        "width":         width,
        "height":        height,
    })
