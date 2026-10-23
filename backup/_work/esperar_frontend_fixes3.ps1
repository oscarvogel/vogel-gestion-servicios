$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$uuid = '7lnwdgdqpattc6bhkcij5d9w'

function Get-Bundle {
  $html = (Invoke-WebRequest -Uri 'https://gestion-vogel.186.5.245.12.sslip.io/' -UseBasicParsing).Content
  $js = @([regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.js') | ForEach-Object { $_.Value } | Select-Object -Unique)
  $css = @([regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.css') | ForEach-Object { $_.Value } | Select-Object -Unique)
  return @{ js = $js[0]; css = $css[0] }
}

$listo = $false
for ($i = 0; $i -lt 45; $i++) {
  $d = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid" -Headers $h -Method Get
  $b = Get-Bundle
  $jsOk = $false
  $cssOk = $false
  try {
    $body = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$($b.js)" -UseBasicParsing).Content
    $jsOk = ($body -match 'allSettled')
  } catch {}
  try {
    $css = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$($b.css)" -UseBasicParsing).Content
    $cssOk = ($css -match '\.technician-picker\{position:relative')
  } catch {}
  Write-Output ("[{0:HH:mm:ss}] status={1} js={2} (fix={3}) css={4} (fix={5})" -f (Get-Date), $d.status, $b.js, $jsOk, $b.css, $cssOk)
  if ($jsOk -and $cssOk) { $listo = $true; break }
  Start-Sleep -Seconds 20
}

if (-not $listo) {
  Write-Output '== el bundle nuevo no quedo servido; logs del frontend:'
  $logs = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid/logs?lines=80" -Headers $h -Method Get
  ($logs.logs -split "`n") | Select-Object -Last 50
}
