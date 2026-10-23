$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$salida = 'C:\Programacion\vogel-gestion\backup\_work\deploy_monitor.txt'
"inicio $(Get-Date -Format 'HH:mm:ss')" | Out-File $salida -Encoding utf8

for ($i = 0; $i -lt 80; $i++) {
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
    $nuevo = ($body -match 'allSettled')
  } catch {}
  Add-Content $salida ("[{0:HH:mm:ss}] {1} | bundle={2} nuevo={3}" -f (Get-Date), ($linea -join ' '), $js[0], $nuevo)
  if ($nuevo) { Add-Content $salida 'LISTO: bundle nuevo servido'; break }
  Start-Sleep -Seconds 20
}
