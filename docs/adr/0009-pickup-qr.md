# 0009. Pickup QR as a convenience over a server-validated code

Status: accepted (2026-11-10)

## Context

A reservation already has a one-time pickup code that the shop owner types together with the
reservation reference. Typing is slow at a counter. We want a QR the customer shows and the
owner scans, without creating a second way to confirm a pickup.

## Decision

- The QR encodes `sobracero:pickup:v1:<reservationId>:<CODE>`. It only carries the two values
  the owner would otherwise type. Scanning fills the form; the owner still presses confirm.
- The server remains the only authority. `POST /reservations/{id}/pickup` checks that the
  signed-in user owns the shop and that the reservation is still `reserved`; the status change
  is a conditional update, so scanning the same QR twice, or two phones scanning at once, picks
  the reservation up exactly once (covered by `tests/test_concurrency.py`).
- The payload is parsed strictly (fixed prefix, version, numeric reference, 8 hex characters).
  Any other QR is rejected with a message.
- Generation happens in the customer's browser with the `qrcode` package. The SVG is built from
  paths, never injected as HTML, with fixed black-on-white colors so it scans in dark mode.
- Scanning uses the browser `BarcodeDetector` API with the camera when it exists. Where it does
  not (for example Firefox), the owner types the values; nothing else changes.

## Consequences

- New dependency: `qrcode` (MIT, no native code) and its types as a dev dependency. It was
  preferred to a hand-written encoder because QR error correction is easy to get subtly wrong.
- The QR contains the one-time code, so it is a secret held by the customer. It does not certify
  that the food is safe, and it is not a tax document.
- No camera library is added; browsers without `BarcodeDetector` use manual entry.
