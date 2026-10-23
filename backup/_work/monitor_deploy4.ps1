$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$salida = 'C:\Programacion\vogel-gestion\backup\_work\deploy_monitor4.txt'
"inicio $(Get-Date -Format 'HH:mm:ss')" | Out-File $salida -Encoding utf8
$viejoJs = 'index-DNQRQQS2.js'
$viejoCss = 'index-DaC-MSIN.css'

for ($i = 0; $i -lt 90; $i++) {
  $deps = Invoke-RestMethod -Uri "$api/api/v1/deployments" -Headers $h -Method Get
  $linea = @()
  foreach ($d in ($deps | Select-Object -First 5)) {
    $linea += "$($d.id)[$($d.application_name.Split(':')[0])]=$($d.status)"
  }
  $html = (Invoke-WebRequest -Uri 'https://gestion-vogel.186.5.245.12.sslip.io/' -UseBasicParsing).Content
  $js = @([regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.js') | ForEach-Object { $_.Value } | Select-Object -Unique)
  $css = @([regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.css') | ForEach-Object { $_.Value } | Select-Object -Unique)
  $nuevo = ($js[0] -ne "assets/$viejoJs") -or ($css[0] -ne "assets/$viejoCss")
  Add-Content $salida ("[{0:HH:mm:ss}] {1} | js={2} css={3} nuevo={4}" -f (Get-Date), ($linea -join ' '), $js[0], $css[0], $nuevo)
  if ($nuevo) {
    # El bundle nuevo tiene que traer el chip Inactivo y el input con fondo del sitio.
    try {
      $jsBody = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$($js[0])" -UseBasicParsing).Content
      $cssBody = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$($css[0])" -UseBasicParsing).Content
      $chip = $jsBody -match 'technician-chip--inactive'
      $input = $cssBody -match '\.technician-assign input\[data-v-[a-z0-9]+\]\{width:100%;background'
      Add-Content $salida ("   chip Inactivo={0} input con fondo={1}" -f $chip, $input)
      if ($chip -and $input) { Add-Content $salida 'LISTO: bundle con los ajustes de UI'; break }
    } catch {
      Add-Content $salida "   (aun no se puede leer el asset)"
    }
  }
  Start-Sleep -Seconds 20
}
