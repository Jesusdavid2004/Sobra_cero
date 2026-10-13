# Live demo script

## Prepare

1. Start the local stack and seed it as described in
   [`deployment.md`](./deployment.md).
2. Confirm `/health` and `/ready` both return success.
3. Open `http://localhost:3000/en`. Use a browser with Chromium for the
   Playwright-style demo.
4. For expiry scanning, use a lot photo with a clearly readable printed date.
   The default local AI provider is deterministic mock mode, so OCR results are
   simulated rather than evidence of a real provider's recognition accuracy.

## Demonstrate the marketplace

1. On the home page, switch from English to Spanish and back. Cycle the theme
   through light and dark and point out that the preference is persisted.
2. Log in as the seeded business account, or register a development-only
   business account.
3. In `/en/shop`, select **New lot**. Publish a lot using the seeded shop and
   product, a positive quantity, a discount, and an expiry time.
4. On the lot detail page, show the current stock and the expiry-date scan
   review panel. If a photo is attached, run a scan and explain that the
   suggested date cannot change inventory until an authorized user confirms
   it. Rejecting leaves the lot unchanged.
5. Log out. Register or log in as a customer and open the lot in the public
   storefront. Reserve a quantity; record the displayed reservation reference
   and pickup code.
6. Log out and return to the owning business account. In the dashboard's
   **Confirm a customer pickup** form, enter both values. The success message
   demonstrates that the reservation is completed by the shop.
7. Optionally show forecast/risk results after loading sample sales history.
   Explain that the score and quantities are computed by application/model
   logic; AI text is qualitative.

## Automated browser coverage

`app-frontend/e2e/publish-to-pickup.spec.ts` exercises lot publication,
customer reservation, shop pickup confirmation, and locale/theme changes with
a deterministic mocked API. It validates frontend behavior without requiring
live database, object-storage, or AI services. Backend authorization and
reservation integration behavior are tested separately by the Python suite.
