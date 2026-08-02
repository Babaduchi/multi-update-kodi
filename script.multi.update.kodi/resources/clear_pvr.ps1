param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseDirectory,

    [Parameter(Mandatory = $true)]
    [string]$KodiExecutable,

    [Parameter(Mandatory = $true)]
    [int]$KodiProcessId
)

$ErrorActionPreference = "Stop"
$logPath = Join-Path $env:TEMP "kodi-multi-update.log"

function Write-MultiUpdateLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logPath -Value "$timestamp $Message"
}

try {
    Write-MultiUpdateLog "Waiting for Kodi process $KodiProcessId to exit."
    $deadline = (Get-Date).AddMinutes(2)

    while ((Get-Process -Id $KodiProcessId -ErrorAction SilentlyContinue) -and
           ((Get-Date) -lt $deadline)) {
        Start-Sleep -Milliseconds 500
    }

    if (Get-Process -Id $KodiProcessId -ErrorAction SilentlyContinue) {
        throw "Kodi did not exit within two minutes; no PVR data was removed."
    }

    # Give Windows time to release Kodi's final SQLite handles.
    Start-Sleep -Seconds 1

    $databases = @(
        Get-ChildItem -LiteralPath $DatabaseDirectory -Filter "TV*.db" -File
        Get-ChildItem -LiteralPath $DatabaseDirectory -Filter "Epg*.db" -File
    ) | Sort-Object -Property FullName -Unique

    if ($databases.Count -eq 0) {
        Write-MultiUpdateLog "No TV*.db or Epg*.db files were present."
    } else {
        foreach ($database in $databases) {
            Remove-Item -LiteralPath $database.FullName -Force
            Write-MultiUpdateLog "Removed $($database.FullName)."
        }
    }

    Write-MultiUpdateLog "Restarting Kodi."
    Start-Process -FilePath $KodiExecutable
} catch {
    Write-MultiUpdateLog "ERROR: $($_.Exception.Message)"

    # Always reopen Kodi, even if cleanup fails.
    if (Test-Path -LiteralPath $KodiExecutable -PathType Leaf) {
        Start-Process -FilePath $KodiExecutable
    }
}
