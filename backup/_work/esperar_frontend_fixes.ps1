$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$uuid = '7lnwdgdqpattc6bhkcij5d9w'

for ($i = 0; $i -lt 40; $i++) {
  $d = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid" -Headers $h -Method Get
  $estado = $d.status
  Write-Output ("[{0:HH:mm:ss}] frontend=$estado" -f (Get-Date))
  if ($estado -match 'running:healthy|running:unknown|exited:success') { Write-Output 'LISTO'; break }
  Start-Sleep -Seconds 15
}

# El bundle publicado es la prueba de que la build nueva quedo servida.
$index = Invoke-WebRequest -Uri 'https://gestion-vogel.186.5.245.12.sslip.io/' -UseBasicParsing
$html = $index.Content
$js = [regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.js') | ForEach-Object { $_.Value } | Select-Object -Unique
$css = [regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.css') | ForEach-Object { $_.Value } | Select-Object -Unique
Write-Output "== bundle: $($js -join ', ') $($css -join ', ')"

foreach ($f in $js) {
  $body = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$f" -UseBasicParsing).Content
  Write-Output ("   {0}: technician-picker={1} allSettled={2} nuevaOT={3}" -f $f,
    ($body -match 'technician-picker'),
    ($body -match 'allSettled'),
    ($body -match 'Nueva recepci'))
}
foreach ($f in $css) {
  $body = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$f" -UseBasicParsing).Content
  Write-Output ("   {0}: technician-picker position:relative={1}" -f $f, ($body -match '\.technician-picker\{position:relative'))
}
