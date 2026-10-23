$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$salida = 'C:\Programacion\vogel-gestion\backup\_work\deploy_monitor2.txt'
"inicio $(Get-Date -Format 'HH:mm:ss')" | Out-File $salida -Encoding utf8

for ($i = 0; $i -lt 90; $i++) {
  $deps = Invoke-RestMethod -Uri "$api/api/v1/deployments" -Headers $h -Method Get
  $linea = @()
  foreach ($d in ($deps | Select-Object -First 6)) {
    $linea += "$($d.id)[$($d.application_name.Split(':')[0])]=$($d.status)"
  }
  $html = (Invoke-WebRequest -Uri 'https://gestion-vogel.186.5.245.12.sslip.io/' -UseBasicParsing).Content
  $js = @([regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.js') | ForEach-Object { $_.Value } | Select-Object -Unique)
  $nuevo = $false
  try {
    $body = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$($js[0])" -UseBasicParsing).Content
    # El fix de sesion deja un rastro en el bundle: el select-company del bootstrap.
    $nuevo = ($body -match 'activeCompany') -and ($body -match 'company_slug')
  } catch {}
  # El backend: el endpoint de technicians tiene que responder 401 sin token (o 200 con token).
  $apiOk = $false
  try {
    $r = Invoke-WebRequest -Uri 'https://gestion-vogel.186.5.245.12.sslip.io/api/v1/work-orders/statuses' -UseBasicParsing -ErrorAction Stop
    $apiOk = $true
  } catch {
    if ($_.Exception.Response.StatusCode.value__ -in @(401, 409)) { $apiOk = $true }
  }
  Add-Content $salida ("[{0:HH:mm:ss}] {1} | bundle={2} nuevo={3} api={4}" -f (Get-Date), ($linea -join ' '), $js[0], $nuevo, $apiOk)
  if ($nuevo -and $apiOk) { Add-Content $salida 'LISTO'; break }
  Start-Sleep -Seconds 20
}
