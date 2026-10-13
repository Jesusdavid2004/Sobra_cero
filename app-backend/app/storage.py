"""S3-compatible object storage adapter backed by MinIO.

The client is created lazily so importing this module never requires the
storage service to be reachable (tests and local development can run without
MinIO unless an image is actually uploaded).
"""

from __future__ import annotations

from io import BytesIO

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import ClientError
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.domain.exceptions import InvalidImageError
from app.domain.rules import (
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_UPLOAD_BYTES,
    SIGNED_IMAGE_URL_TTL_SECONDS,
)

IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "JPEG"),
    "PNG": ("image/png", "PNG"),
    "WEBP": ("image/webp", "WEBP"),
}


def sanitize_image(data: bytes, declared_content_type: str) -> tuple[bytes, str]:
    """Validate, orient, and re-encode a supported image without metadata."""
    output = BytesIO()
    try:
        with Image.open(BytesIO(data)) as source:
            image_format = source.format
            if image_format not in IMAGE_FORMATS or getattr(source, "n_frames", 1) != 1:
                raise InvalidImageError("Only static JPEG, PNG, and WebP images are supported")
            content_type, output_format = IMAGE_FORMATS[image_format]
            if content_type != declared_content_type:
                raise InvalidImageError("Image content does not match its declared type")
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise InvalidImageError("Image dimensions exceed the supported limit")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
            clean_image = oriented.convert("RGBA" if has_alpha else "RGB")
            if output_format == "JPEG":
                clean_image.convert("RGB").save(output, format=output_format, quality=90, optimize=True)
            elif output_format == "WEBP":
                clean_image.save(output, format=output_format, quality=90, method=6)
            else:
                clean_image.save(output, format=output_format, optimize=True)
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise InvalidImageError("Uploaded image is corrupt or cannot be decoded") from exc

    sanitized = output.getvalue()
    if len(sanitized) > MAX_IMAGE_UPLOAD_BYTES:
        raise InvalidImageError("Sanitized image exceeds the supported size limit")
    return sanitized, content_type


class ObjectStorage:
    """Thin wrapper around an S3-compatible object storage service."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        public_url: str,
        secure: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.public_url = public_url.rstrip("/")
        self.secure = secure
        self._client: BaseClient | None = None
        self._signing_client: BaseClient | None = None

    @property
    def client(self) -> BaseClient:
        """Lazily build the boto3 S3 client on first use."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=f"{'https' if self.secure else 'http'}://{self.endpoint}",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                region_name="us-east-1",
            )
        return self._client

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist yet."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        """Store an object without making it publicly readable."""
        self.ensure_bucket()
        self.client.put_object(Bucket=self.bucket, Key=key, Body=BytesIO(data), ContentType=content_type)

    def signed_url(self, key: str) -> str:
        """Create a short-lived read URL that is reachable from the user's network."""
        if self._signing_client is None:
            self._signing_client = boto3.client(
                "s3",
                endpoint_url=self.public_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                region_name="us-east-1",
            )
        return str(
            self._signing_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=SIGNED_IMAGE_URL_TTL_SECONDS,
            )
        )

    def download(self, key: str) -> tuple[bytes, str]:
        """Read a private image for a server-side vision request."""
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            return (
                body.read(MAX_IMAGE_UPLOAD_BYTES + 1),
                str(response.get("ContentType", "application/octet-stream")),
            )
        finally:
            body.close()


_storage: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    """Return the application-wide object storage singleton."""
    global _storage
    if _storage is None:
        _storage = ObjectStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            public_url=settings.minio_public_url,
            secure=settings.minio_secure,
        )
    return _storage
