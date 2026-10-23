$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$front = '7lnwdgdqpattc6bhkcij5d9w'
$back = 'ssknzmign82c2uapblj1x8le'

$d = Invoke-RestMethod -Uri "$api/api/v1/applications/$front" -Headers $h -Method Get
Write-Output '== FRONTEND: env / build args'
foreach ($e in $d.envs) {
  if ($e.name -match 'BACKEND|URL|NETWORK|ALIAS') {
    "env $($e.name) = $($e.value)"
  }
}
Write-Output "custom_network_aliases: $($d.custom_network_aliases)"
Write-Output "dockerfile: $($d.dockerfile)"
Write-Output "dockerfile_location: $($d.dockerfile_location)"
Write-Output "build_args: $($d.build_args | ConvertTo-Json -Compress)"
Write-Output "networks: $($d.networks | ConvertTo-Json -Compress)"

Write-Output ''
Write-Output '== BACKEND: nombre y alias'
$b = Invoke-RestMethod -Uri "$api/api/v1/applications/$back" -Headers $h -Method Get
"name: $($b.name)"
"custom_network_aliases: $($b.custom_network_aliases)"
"status: $($b.status)"
