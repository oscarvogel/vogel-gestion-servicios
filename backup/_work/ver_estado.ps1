$ErrorActionPreference = 'Continue'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$back = 'ssknzmign82c2uapblj1x8le'
$front = '7lnwdgdqpattc6bhkcij5d9w'
$db = 'diamcot1wyytezyasugd5biv'

foreach ($pair in @(@{n='backend';u=$back}, @{n='frontend';u=$front}, @{n='database';u=$db})) {
  try {
    $d = Invoke-RestMethod -Uri "$api/api/v1/applications/$($pair.u)" -Headers $h -Method Get
    Write-Output ("{0}: status={1} health={2} sha={3}" -f $pair.n, $d.status, $d.health_status, $d.git_commit_sha)
  } catch {
    try {
      $d = Invoke-RestMethod -Uri "$api/api/v1/databases/$($pair.u)" -Headers $h -Method Get
      Write-Output ("{0} (db): status={1} public={2} port={3}" -f $pair.n, $d.status, $d.is_public, $d.public_port)
    } catch { Write-Output "$($pair.n): $($_.Exception.Message)" }
  }
}

Write-Output ''
Write-Output '== logs del backend (las ultimas lineas son lo mas reciente)'
$logs = Invoke-RestMethod -Uri "$api/api/v1/applications/$back/logs?lines=60" -Headers $h -Method Get
($logs.logs -split "`n") | Where-Object { $_ -match '\S' } | Select-Object -First 30

Write-Output ''
Write-Output '== logs de la base'
$blogs = Invoke-RestMethod -Uri "$api/api/v1/databases/$db/logs?lines=30" -Headers $h -Method Get
($blogs.logs -split "`n") | Where-Object { $_ -match '\S' } | Select-Object -First 20
