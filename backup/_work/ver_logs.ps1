$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }

$d = Invoke-RestMethod -Uri "$api/api/v1/deployments?uuid=ssknzmign82c2uapblj1x8le&perPage=1" -Headers $h -Method Get
$ult = @($d)[0]
Write-Output "deployment_id=$($ult.deployment_uuid) status=$($ult.status) commit=$($ult.commit) branch=$($ult.branch)"

$logs = Invoke-RestMethod -Uri "$api/api/v1/deployments/$($ult.deployment_uuid)/logs?lines=120" -Headers $h -Method Get
$texto = ($logs | ForEach-Object { $_.output }) -join "`n"
$lineas = $texto -split "`n"
$lineas | Where-Object { $_ -match 'alembic|migrat|0027|Technician|technician|ERROR|error|Traceback|running|Uvicorn|Application startup' } | Select-Object -Last 40
