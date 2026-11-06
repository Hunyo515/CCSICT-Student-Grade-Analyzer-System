# Restart only this project's loopback server after changing local configuration.
$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$appPython = Join-Path $appRoot 'venv\Scripts\python.exe'
$listeners = @(Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
    $serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    $launcherProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($serverProcess.ParentProcessId)"
    if ($listener.LocalAddress -ne '127.0.0.1' -or $serverProcess.CommandLine -notmatch 'run\.py' -or $launcherProcess.ExecutablePath -ne $appPython) {
        throw 'Port 5000 belongs to an unexpected process. Nothing was stopped.'
    }
}
$projectCommand = '^\s*"?' + [regex]::Escape($appPython) + '"?\s+"?run\.py"?\s*$'
$projectProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $projectCommand })
$projectLaunchers = @($projectProcesses | Where-Object { $_.ExecutablePath -eq $appPython })
$launcherIds = @($projectLaunchers | ForEach-Object { $_.ProcessId })
$projectChildren = @($projectProcesses | Where-Object { $launcherIds -contains $_.ParentProcessId })
# Windows virtual-environment launchers and their Python children may both survive
# a listener-only stop. Stop every exact project launcher, then its known children.
foreach ($projectProcess in $projectLaunchers) { Stop-Process -Id $projectProcess.ProcessId -ErrorAction SilentlyContinue }
foreach ($projectProcess in $projectChildren) { Stop-Process -Id $projectProcess.ProcessId -ErrorAction SilentlyContinue }
$remainingListeners = @(Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)
if ($remainingListeners.Count -gt 0) { throw 'Port 5000 is still in use. No replacement server was started.' }
$logs = Join-Path $appRoot 'audit\rebuild'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
Start-Process -FilePath $appPython -ArgumentList 'run.py' -WorkingDirectory $appRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'server.stdout.log') -RedirectStandardError (Join-Path $logs 'server.stderr.log') | Out-Null
Write-Output 'Local app started at http://127.0.0.1:5000/. Check audit/rebuild/server.stderr.log if it does not respond.'
