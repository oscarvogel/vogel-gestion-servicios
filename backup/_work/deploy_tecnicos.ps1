$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$apps = @(
  @{ uuid = 'ssknzmign82c2uapblj1x8le'; name = 'backend' },
  @{ uuid = '7lnwdgdqpattc6bhkcij5d9w'; name = 'frontend' }
)

foreach ($app in $apps) {
  $current = Invoke-RestMethod -Uri "$api/api/v1/applications/$($app.uuid)" -Headers $h -Method Get
  Write-Output "== $($app.name) ($($app.uuid)) branch=$($current.git_branch) sha=$($current.git_commit_sha) status=$($current.status)"
}

foreach ($app in $apps) {
  $body = @{ git_branch = 'feature/cyberbrain-migracion'; git_commit_sha = 'HEAD' } | ConvertTo-Json
  $null = Invoke-RestMethod -Uri "$api/api/v1/applications/$($app.uuid)" -Headers $h -Method Patch -Body $body -ContentType 'application/json'
  Write-Output "== $($app.name): branch y commit actualizados"
}

foreach ($app in $apps) {
  $null = Invoke-RestMethod -Uri "$api/api/v1/deploy?uuid=$($app.uuid)&force=true" -Headers $h -Method Post -ContentType 'application/json'
  Write-Output "== $($app.name): deploy pedido"
}
