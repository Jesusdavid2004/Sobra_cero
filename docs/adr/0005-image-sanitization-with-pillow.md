# ADR 0005: Sanitize uploaded images with Pillow

## Status

Accepted

## Context

Lot images are stored privately and may be sent to a configured AI vision
provider. Checking only file signatures does not prove that image data is
decodable, and forwarding original image bytes can expose EXIF metadata.
Images also need bounded dimensions and frame counts to limit resource use.

## Decision

Use Pillow at the upload boundary to decode only supported static JPEG, PNG,
and WebP files, enforce a pixel limit, apply EXIF orientation, and re-encode
pixels before private storage. Validate and sanitize stored bytes again before
sending them to an AI vision provider.

## Consequences

Pillow is an additional pinned backend dependency. Uploads incur decode and
re-encode CPU cost, but stored and provider-bound images have validated
content, no inherited EXIF metadata, and bounded dimensions.
