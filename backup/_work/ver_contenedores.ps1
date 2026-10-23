$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

Write-Output '== servidores'
try {
  $servers = Invoke-RestMethod -Uri "$api/api/v1/servers" -Headers $h -Method Get
  $servers | ForEach-Object { "uuid=$($_.uuid) name=$($_.name) ip=$($_.ip)" }
  foreach ($s in $servers) {
    Write-Output "== contenedores de $($s.name)"
    try {
      $c = Invoke-RestMethod -Uri "$api/api/v1/servers/$($s.uuid)/containers" -Headers $h -Method Get
      $c | Where-Object { $_.name -match 'vogel|backend|frontend' } | ForEach-Object {
        "  name=$($_.name) status=$($_.status) ip=$($_.ip) aliases=$($_.custom_network_aliases)"
      }
    } catch { "   (no se pudo listar: $($_.Exception.Message))" }
  }
} catch { "servidores: $($_.Exception.Message)" }
