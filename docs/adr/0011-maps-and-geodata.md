# 0011. Leaflet, a place directory and no PostGIS yet

Status: accepted (2026-11-16)

## Context

The product needs an interactive map of businesses in Pasto, a search by place name and a clear
difference between affiliated shops and businesses found elsewhere.

## Decision

- **Map library:** Leaflet with marker clustering, loaded only in the browser. Tiles come from a
  configurable URL; the default is the public OpenStreetMap tile server with the required
  attribution. That server is for light use, so the guide lists hosted alternatives to switch to
  before real traffic.
- **Data model:** `places` are served by one read model that merges affiliated shops and external
  businesses. Every place carries `affiliation` (`affiliated`, `prospect`, `discovered`), its
  `source`, `source_url` and `last_seen_at`. An external business is never shown as affiliated.
- **Geocoding:** a `GeocodingProvider` port. The first adapter is Nominatim, limited to one
  request per second, identified by User-Agent, cached, without autocomplete. A deterministic
  fake serves tests and offline demos.
- **Spatial queries:** bounding box and haversine in code over indexed latitude and longitude.
  PostGIS is **not** adopted: the data is thousands of rows, tests run on SQLite, and no polygon
  query exists. Revisit above roughly 50,000 places or when a polygon or routing query appears.
- **Opportunity indicators** use only verifiable records: published promotions, offers registered
  by affiliated shops, receivers that exist, and counts of places per area. Nothing infers waste
  from a location or a price.

## Consequences

- The map works with no paid service. The tile policy is a known limit.
- Distances remain straight-line estimates and are labelled as such.
- Moving to PostGIS later means replacing one repository, not the API.
