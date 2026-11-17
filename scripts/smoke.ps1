$ErrorActionPreference = "Stop"
$base = "http://localhost:8000/api/v1"
$suffix = [guid]::NewGuid().ToString("N")

$businessBody = @{
  email = "smoke-business-$suffix@example.com"
  password = "password123"
  role = "business"
} | ConvertTo-Json
$businessToken = (
  Invoke-RestMethod -Method Post -Uri "$base/auth/register" -ContentType "application/json" -Body $businessBody
).access_token
$businessHeaders = @{ Authorization = "Bearer $businessToken" }

$shopBody = @{
  name = "Smoke test shop $suffix"
  description = "Created by the smoke test."
  latitude = 4.7
  longitude = -74.0
} | ConvertTo-Json
$shop = Invoke-RestMethod -Method Post -Uri "$base/shops" -Headers $businessHeaders -ContentType "application/json" -Body $shopBody

$productBody = @{
  name = "Smoke test product"
  description = "Created by the smoke test."
  category = "bakery"
} | ConvertTo-Json
$product = Invoke-RestMethod -Method Post -Uri "$base/shops/$($shop.id)/products" -Headers $businessHeaders -ContentType "application/json" -Body $productBody

$lotBody = @{
  shop_id = $shop.id
  product_id = $product.id
  title = "Smoke test lot"
  description = "Created by the smoke test."
  quantity = 2
  original_price_cents = 1000
  discount_percent = 30
  expires_at = [DateTime]::UtcNow.AddDays(1).ToString("o")
} | ConvertTo-Json
$lot = Invoke-RestMethod -Method Post -Uri "$base/lots" -Headers $businessHeaders -ContentType "application/json" -Body $lotBody
$publicLots = Invoke-RestMethod -Method Get -Uri "$base/lots"
if (-not ($publicLots | Where-Object { $_.id -eq $lot.id })) {
  throw "Published lot was not visible in the public storefront."
}

$customerBody = @{
  email = "smoke-customer-$suffix@example.com"
  password = "password123"
  role = "customer"
} | ConvertTo-Json
$customerToken = (
  Invoke-RestMethod -Method Post -Uri "$base/auth/register" -ContentType "application/json" -Body $customerBody
).access_token
$customerHeaders = @{ Authorization = "Bearer $customerToken" }
$reservationBody = @{ quantity = 1 } | ConvertTo-Json
$reservation = Invoke-RestMethod -Method Post -Uri "$base/lots/$($lot.id)/reserve" -Headers $customerHeaders -ContentType "application/json" -Body $reservationBody
if ($reservation.status -ne "reserved" -or $reservation.pickup_code.Length -ne 8) {
  throw "Reservation did not return the expected status and pickup code."
}

$remainingLot = Invoke-RestMethod -Method Get -Uri "$base/lots/$($lot.id)"
if ($remainingLot.quantity -ne 1) {
  throw "Reservation did not reduce the available lot quantity."
}

Write-Host "Smoke test passed: business published a lot and customer reserved it with pickup code $($reservation.pickup_code)."
