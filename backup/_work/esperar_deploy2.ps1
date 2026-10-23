$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$apps = @(
  @{ uuid = 'ssknzmign82c2uapblj1x8le'; name = 'backend' },
  @{ uuid = '7lnwdgdqpattc6bhkcij5d9w'; name = 'frontend' }
)

for ($i = 0; $i -lt 60; $i++) {
  $linea = @()
  $todosListos = $true
  foreach ($app in $apps) {
    $d = Invoke-RestMethod -Uri "$api/api/v1/deployments?uuid=$($app.uuid)&perPage=1" -Headers $h -Method Get
    $ult = @($d)[0]
    $estado = "$($ult.status)"
    $linea += "$($app.name)=$estado"
    if ($estado -ne 'successful') { $todosListos = $false }
  }
  Write-Output ("[{0:HH:mm:ss}] {1}" -f (Get-Date), ($linea -join ' | '))
  if ($todosListos) { Write-Output 'LISTO'; break }
  Start-Sleep -Seconds 20
}
