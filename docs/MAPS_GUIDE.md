# Maps guide

How the map, the directory and the place search work, and what they do not claim.
Decisions are in ADR 0011.

## What the map shows

The `/map` page merges three kinds of points, kept visibly apart:

| Marker | Meaning | Source |
| --- | --- | --- |
| Solid disc | **Affiliated shop**: it registered itself on SobraCero. An orange number is how many offers are live. | The shop's own record |
| Dashed ring | **Business found in a public source**: not affiliated, never shown as a partner. | A connector (for example OpenStreetMap) |
| Handshake icon | **Receiving organization** that created a profile. | The organization's own profile |

Every place card says its affiliation, whether a person verified it, where the information came
from, a link to the source record, and when it was last seen. Data older than 72 hours is flagged
as possibly out of date.

An affiliated shop is placed under the category of what it sells: a restaurant whose products are
mostly bakery shows as a bakery; a supermarket stays a supermarket.

## Layers and filters

Layers: affiliated shops, found in public sources, receiving organizations. Filters: name (accents
ignored), category, only shops with live offers, and an opt-in to include demonstration data. The
opportunity overlay and the promotions panel are separate (below).

## Opportunity areas

"Where activity is concentrated" counts verifiable records per cell of about 1 km: affiliated shops,
live offers, receivers and discovered businesses. A cell with discovered businesses and no
affiliated shop is marked as a place to invite. **It never estimates waste or demand**: location
and price are not evidence of surplus.

## Public promotions

Prices that public catalogs published recently. A promotion is not a surplus and says nothing about
stock or expiry. These are listed, not placed on the map, because a catalog page has no location.

## Place search (geocoding)

`GET /api/v1/geo/search?q=` goes through a `GeocodingProvider` port. The Nominatim adapter follows
its usage policy (checked 2026-11-16): at most one request per second, an identifying User-Agent,
results cached for a day, no autocomplete (the search runs only on submit) and attribution shown.
The endpoint is also limited to 20 requests per minute per client. Do not use it for bulk
geocoding. `GEOCODER_PROVIDER=fake` serves a small gazetteer for tests and offline demos.

To change provider, implement `search(query, limit)` returning `GeocodeResult` items and select it
in `build_search_geocode_use_case`.

## Tiles and attribution

The default tile server is the public OpenStreetMap one, which is for light use. Before real
traffic set `NEXT_PUBLIC_MAP_TILE_URL` (and `NEXT_PUBLIC_MAP_ATTRIBUTION`) to a hosted provider
and keep that provider's attribution. OpenStreetMap data requires the credit "© OpenStreetMap
contributors"; the map and each externally sourced place carry it.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/map/places` | Places by area, layers, categories, name, offers and demo opt-in. Public. |
| `GET` | `/api/v1/map/opportunities` | Counts per cell. Public. |
| `GET` | `/api/v1/map/promotions` | Fresh public promotions. Public. |
| `GET` | `/api/v1/geo/search` | Place search. Rate limited. |

`/map/places` returns `approximate`-free data (coordinates are stored values), `counts` per layer
and the attribution to display. Rejected businesses and shops without a location are never returned.

## Demonstration data

`python scripts/seed_pasto_demo.py` loads ten invented businesses for Pasto into a source of kind
`demo`. They are flagged, hidden unless the visitor opts in, labelled on their card, and are never
affiliated. The script writes no products or prices, so nothing can look like a real promotion.

## PostGIS

Not used. The queries are a bounding box and a straight-line distance over thousands of rows, tests
run on SQLite and there is no polygon query. Revisit above roughly 50,000 places or when routing
or polygons appear; only `map_repository.py` would change.

## Limits

- Distances are straight-line estimates; travel time assumes a fixed average speed.
- No routing, no multi-stop optimization.
- The live Overpass query could not be verified from the development machine; the map was verified
  with a recorded response and with demonstration data.
