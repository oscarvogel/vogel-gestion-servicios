$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$apps = @(
  @{ uuid = 'ssknzmign82c2uapblj1x8le'; name = 'backend' },
  @{ uuid = '7lnwdgdqpattc6bhkcij5d9w'; name = 'frontend' }
)

for ($i = 0; $i -lt 40; $i++) {
  $linea = @()
  $todosListos = $true
  foreach ($app in $apps) {
    $d = Invoke-RestMethod -Uri "$api/api/v1/applications/$($app.uuid)" -Headers $h -Method Get
    $estado = $d.status
    $linea += "$($app.name)=$estado"
    if ($estado -notmatch 'running:healthy|running:unknown|exited:success') { $todosListos = $false }
  }
  Write-Output ("[{0:HH:mm:ss}] {1}" -f (Get-Date), ($linea -join ' | '))
  if ($todosListos) { Write-Output 'LISTO'; break }
  Start-Sleep -Seconds 15
}
