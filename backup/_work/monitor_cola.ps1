# Monitorea la cola de deploys de Coolify hasta que terminen los dos de staging.
# La cola es COMPARTIDA entre proyectos: hay deploys de otros delante.
$ErrorActionPreference = 'Stop'
$api = 'https://coolify.vogelconsultoria.com.ar'
$h = @{ Authorization = "Bearer $((Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim())" }

$backend = 'ssknzmign82c2uapblj1x8le'
$frontend = '7lnwdgdqpattc6bhkcij5d9w'

function Get-Deployments {
    try { Invoke-RestMethod -Uri "$api/api/v1/deployments" -Headers $h -Method Get } catch { @() }
}

$deadline = (Get-Date).AddMinutes(45)
$last = ''
while ((Get-Date) -lt $deadline) {
    $deps = Get-Deployments
    $nuestro = $deps | Where-Object { $_.application_id -eq $backend -or $_.application_id -eq $frontend -or $_.application_name -like '*staging*' }
    $line = ($deps | Select-Object -First 6 | ForEach-Object {
            "{0}:{1}:{2}" -f $_.id, $_.status, ($_.application_name -replace 'vogel-gestion-servicios-', '')
        }) -join '  |  '
    if ($line -ne $last) {
        Write-Output ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $line)
        $last = $line
    }
    $nuestro | ForEach-Object {
        if ($_.status -in @('finished', 'failed', 'cancelled', 'error')) {
            Write-Output ("  >> deploy {0} {1} = {2}  commit={3}" -f $_.id, $_.application_name, $_.status, $_.commit)
        }
    }
    $pending = $nuestro | Where-Object { $_.status -in @('queued', 'in_progress') }
    if (-not $pending) {
        Write-Output '--- los deploys de staging salieron de la cola ---'
        break
    }
    Start-Sleep -Seconds 20
}

Write-Output '=== estado final de la cola ==='
$deps = Get-Deployments
$deps | Select-Object -First 8 | ForEach-Object {
    Write-Output ("  {0} | {1} | {2} | commit={3}" -f $_.id, $_.status, $_.application_name, $_.commit)
}
