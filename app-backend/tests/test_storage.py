from io import BytesIO
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from app.domain.exceptions import InvalidImageError
from app.storage import ObjectStorage, sanitize_image


def create_image(format_name: str, **options: object) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format=format_name, **options)
    return buffer.getvalue()


def test_signed_image_urls_use_public_endpoint_and_short_ttl():
    storage = ObjectStorage(
        endpoint="localstack:4566",
        access_key="test",
        secret_key="test",
        bucket="lots",
        public_url="http://localhost:4566",
    )

    signed_url = storage.signed_url("lots/1/random-key")
    parsed_url = urlsplit(signed_url)

    assert parsed_url.hostname == "localhost"
    assert parsed_url.path == "/lots/lots/1/random-key"
    assert parse_qs(parsed_url.query)["X-Amz-Expires"] == ["300"]


def test_sanitize_image_accepts_valid_png_and_reencodes_without_metadata() -> None:
    sanitized, content_type = sanitize_image(create_image("PNG"), "image/png")

    with Image.open(BytesIO(sanitized)) as result:
        assert content_type == "image/png"
        assert result.format == "PNG"
        assert result.getexif() == {}


def test_sanitize_image_removes_exif_metadata() -> None:
    image = Image.new("RGB", (2, 2), "white")
    exif = image.getexif()
    exif[270] = "private metadata"
    original = BytesIO()
    image.save(original, format="JPEG", exif=exif)

    sanitized, content_type = sanitize_image(original.getvalue(), "image/jpeg")

    with Image.open(BytesIO(sanitized)) as result:
        assert content_type == "image/jpeg"
        assert result.getexif() == {}


def test_sanitize_image_rejects_mime_mismatch() -> None:
    with pytest.raises(InvalidImageError):
        sanitize_image(create_image("PNG"), "image/jpeg")


def test_sanitize_image_rejects_corrupt_content_with_valid_mime() -> None:
    with pytest.raises(InvalidImageError):
        sanitize_image(b"\x89PNG\r\n\x1a\nnot a decodable image", "image/png")


def test_sanitize_image_rejects_images_over_pixel_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.storage.MAX_IMAGE_PIXELS", 3)
    with pytest.raises(InvalidImageError, match="dimensions"):
        sanitize_image(create_image("PNG"), "image/png")
