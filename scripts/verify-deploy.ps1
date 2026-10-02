<#
.SYNOPSIS
  Verifica que un ambiente de Coolify sirva realmente el código esperado.

.DESCRIPTION
  Un 200 en la página no dice nada: el frontend puede cargar perfecto con la API rota,
  que fue exactamente como producción cayó el 2026-10-02. Esta comprobación exige, para
  un ambiente, las cuatro cosas:

    1. el HTML entrega un bundle .js;
    2. ese bundle contiene el marcador de texto esperado (ej. "Actividad de hoy");
    3. el proxy /api/ del origen del frontend llega al backend y responde JSON
       (401 en un login inválido, nunca 405 ni HTML);
    4. se puede determinar el modo de API, same-origin o cross-origin.

  Con -Wait no falla al primer intento: reintenta hasta -TimeoutSeconds, que es lo que
  hace falta después de un deploy, porque el contenedor reinicia y contesta a medias.

.PARAMETER Url
  Origen del frontend, sin barra final. Ej: https://servicios.vogelconsultoria.com.ar

.PARAMETER Expected
  Texto que debe aparecer dentro del bundle servido, por ejemplo una clase CSS
  ("attention-strip") o una etiqueta de la pantalla. Sin este parámetro solo se
  comprueban los puntos 3 y 4. Funciona con acentos: el bundle se decodifica
  como UTF-8 explícitamente. Aun así, si podés elegir un marcador ASCII es
  más robusto ante cambios de codificación.

.PARAMETER Wait
  Reintentar hasta que pase o venza el timeout, en vez de fallar en el primer intento.

.EXAMPLE
  .\scripts\verify-deploy.ps1 -Url https://servicios.vogelconsultoria.com.ar -Expected "Requieren atención" -Wait
#>
param(
  [Parameter(Mandatory = $true)][string]$Url,
  [string]$Expected = '',
  [switch]$Wait,
  [int]$TimeoutSeconds = 600,
  [int]$RetrySeconds = 20
)

$ErrorActionPreference = 'Continue'
$Url = $Url.TrimEnd('/')
if (-not $Wait -and $TimeoutSeconds -gt 0) { $TimeoutSeconds = 0 }
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$intentos = 0
$fallos = @()

do {
  $intentos++
  $fallos = @()

  # 1 y 2: el bundle realmente servido contiene lo esperado
  $js = $null
  $tiene = $null
  try {
    $html = (Invoke-WebRequest "$Url/" -UseBasicParsing -TimeoutSec 25 -ErrorAction Stop).Content
    $js = [regex]::Match($html, 'src="([^"]+\.js)"').Groups[1].Value
    if (-not $js) { $fallos += 'el HTML no entrega un bundle .js' }
    else {
      # Ojo: Invoke-WebRequest decodifica el cuerpo con la codificacion que crea
      # conveniente y un .js servido sin charset llega como Latin-1, asi que las
      # tildes del bundle quedan como dos caracteres y cualquier busqueda con texto
      # acentuado da FALSO NEGATIVO. Se baja a disco y se lee como UTF-8.
      $tmp = Join-Path ([IO.Path]::GetTempPath()) ("vgs-bundle-" + [IO.Path]::GetRandomFileName() + ".js")
      try {
        Invoke-WebRequest "$Url$js" -UseBasicParsing -TimeoutSec 60 -OutFile $tmp -ErrorAction Stop
        $bundle = [IO.File]::ReadAllText($tmp, [Text.Encoding]::UTF8)
      } finally {
        if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
      }
      if ($Expected) {
        $tiene = $bundle -match [regex]::Escape($Expected)
        if (-not $tiene) { $fallos += "el bundle no contiene '$Expected'" }
      }
      # Ojo: buscar '/api/v1' da falso positivo porque la URL absoluta también lo
      # contiene. Para el modo hay que buscar la URL absoluta.
      $abs = [regex]::Match($bundle, 'https://api\.[a-z0-9.\-]+/api/v1').Value
      $modo = if ($abs) { "cross-origin -> $abs" } else { 'same-origin -> /api/v1' }
    }
  } catch {
    $fallos += "no se pudo leer el bundle: $($_.Exception.Message.Substring(0, [Math]::Min(80, $_.Exception.Message.Length)))"
  }

  # 3: el proxy /api/ tiene que llegar al backend y devolver JSON
  $apiStatus = 'nochecked'
  try {
    $null = Invoke-WebRequest -Method Post -Uri "$Url/api/v1/auth/login" `
      -ContentType 'application/json' -Body '{"email":"nadie@example.com","password":"x"}' `
      -UseBasicParsing -TimeoutSec 25 -ErrorAction Stop
    $apiStatus = '200 (inesperado: el login deberia rechazar credenciales falsas)'
  } catch {
    $resp = $_.Exception.Response
    $code = if ($resp) { [int]$resp.StatusCode } else { 0 }
    $ct = if ($resp) { [string]$resp.Headers['Content-Type'] } else { '' }
    if ($code -eq 401 -and $ct -match 'json') { $apiStatus = '401 json (el proxy llega al backend)' }
    elseif ($code -eq 405 -or $ct -match 'text/html') {
      $apiStatus = "$code $ct"
      $fallos += "el nginx no tiene la ruta /api/ (bundle y nginx desalineados)"
    } else { $apiStatus = "$code $ct" }
  }

  $marca = if ($fallos.Count -eq 0) { 'OK' } else { 'FALLA' }
  Write-Output ("[{0}] intento {1} {2}  bundle={3}  api={4}  modo={5}" -f `
      (Get-Date -Format 'HH:mm:ss'), $intentos, $marca, $js, $apiStatus, $modo)
  foreach ($f in $fallos) { Write-Output "    - $f" }

  if ($fallos.Count -eq 0) { Write-Output 'RESULTADO: OK'; exit 0 }
  if ((Get-Date) -ge $deadline) { break }
  if ($TimeoutSeconds -gt 0) { Start-Sleep -Seconds $RetrySeconds }
} while ($TimeoutSeconds -gt 0)

Write-Output "RESULTADO: FALLO - $($Url) no cumple la verificacion"
exit 1
