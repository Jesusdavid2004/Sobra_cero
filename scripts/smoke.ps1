$ErrorActionPreference = "Stop"
$base = "http://localhost:8000/api/v1"
$email = "smoke@example.com"
$body = @{ email = $email; password = "password123" } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "$base/auth/register" -ContentType "application/json" -Body $body).access_token
$headers = @{ Authorization = "Bearer $token" }
$shops = Invoke-RestMethod -Method Get -Uri "$base/shops"
Write-Host "Smoke test passed: authenticated user can read $($shops.Count) shops."
