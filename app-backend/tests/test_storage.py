from urllib.parse import parse_qs, urlsplit

from app.storage import ObjectStorage


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
