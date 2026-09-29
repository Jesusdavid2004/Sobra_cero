"""S3-compatible object storage adapter backed by MinIO.

The client is created lazily so importing this module never requires the
storage service to be reachable (tests and local development can run without
MinIO unless an image is actually uploaded).
"""

from __future__ import annotations

from io import BytesIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings


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
        self._client = None

    @property
    def client(self):
        """Lazily build the boto3 S3 client on first use."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=f"{'https' if self.secure else 'http'}://{self.endpoint}",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4"),
                region_name="us-east-1",
            )
        return self._client

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist yet."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Store an object and return its public URL."""
        self.ensure_bucket()
        self.client.put_object(Bucket=self.bucket, Key=key, Body=BytesIO(data), ContentType=content_type)
        return self.url(key)

    def url(self, key: str) -> str:
        return f"{self.public_url}/{self.bucket}/{key}"


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
