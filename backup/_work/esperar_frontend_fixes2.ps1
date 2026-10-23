$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$token = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token" }
$uuid = '7lnwdgdqpattc6bhkcij5d9w'

for ($i = 0; $i -lt 60; $i++) {
  $d = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid" -Headers $h -Method Get
  Write-Output ("[{0:HH:mm:ss}] status={1} sha={2}" -f (Get-Date), $d.status, $d.git_commit_sha)
  $html = (Invoke-WebRequest -Uri 'https://gestion-vogel.186.5.245.12.sslip.io/' -UseBasicParsing).Content
  $js = [regex]::Matches($html, 'assets/index-[A-Za-z0-9_-]+\.js') | ForEach-Object { $_.Value } | Select-Object -Unique
  $body = (Invoke-WebRequest -Uri "https://gestion-vogel.186.5.245.12.sslip.io/$($js[0])" -UseBasicParsing).Content
  if ($body -match 'allSettled') {
    Write-Output "== bundle nuevo servido: $($js[0])"
    break
  }
  Write-Output "   bundle actual: $($js[0]) (todavia sin el fix)"
  Start-Sleep -Seconds 20
}

$logs = Invoke-RestMethod -Uri "$api/api/v1/applications/$uuid/logs?lines=60" -Headers $h -Method Get
Write-Output '--- ultimas lineas del log ---'
($logs.logs -split "`n") | Select-Object -Last 40
