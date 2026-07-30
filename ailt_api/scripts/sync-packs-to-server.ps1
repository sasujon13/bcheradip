# Incrementally sync language pack ZIPs to the Linux server.
# Skips when remote matches local size. Uploads missing packs. Overwrites when local is larger.
# With -CleanOldVersions (default): after sync, keep only the newest local major (e.g. v1.zip)
# on the server and delete stale v2/v3/… for that language.
param(
    [string]$SshHost = "163.227.144.146",
    [string]$SshUser = "sasha",
    [string]$LocalPacksDir = (Join-Path $PSScriptRoot "..\packs"),
    [string]$RemotePacksDir = "/home/sasha/apps/cheradip/bcheradip/ailt_api/packs",
    [switch]$DryRun,
    [switch]$RestartApi,
    [switch]$NoCleanOldVersions
)

# Default: clean stale majors (v2/v3/…) unless -NoCleanOldVersions is set.
$CleanOldVersions = -not $NoCleanOldVersions

$ErrorActionPreference = "Stop"
$LocalPacksDir = (Resolve-Path $LocalPacksDir).Path
$remoteTarget = "${SshUser}@${SshHost}:${RemotePacksDir}"

function Get-PackVersionSortKey {
    param([string]$Stem)
    if ($Stem -match '^v(\d+(?:\.\d+)*)$') {
        return [int]($Matches[1].Split('.')[0])
    }
    return 0
}

function Get-LocalPackManifest {
    param([string]$Root)
    $manifest = [ordered]@{}
    Get-ChildItem -Path $Root -Directory | Sort-Object Name | ForEach-Object {
        $code = $_.Name
        # Prefer a single shipping major: highest vN.zip (new app uses v1).
        $packFile = Get-ChildItem -Path $_.FullName -File -Filter "v*" -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in ".zip", ".json" } |
            Sort-Object { Get-PackVersionSortKey $_.BaseName } -Descending |
            Select-Object -First 1
        if ($packFile) {
            $rel = "$code/$($packFile.Name)"
            $manifest[$rel] = [pscustomobject]@{
                RelativePath = $rel
                Code         = $code
                FileName     = $packFile.Name
                LocalPath    = $packFile.FullName
                SizeBytes    = $packFile.Length
            }
        }
    }
    return $manifest
}

function Get-RemotePackManifest {
    param(
        [string]$User,
        [string]$HostName,
        [string]$RemoteDir
    )
    $remote = @{}
    $findCmd = "find '$RemoteDir' -type f \( -name 'v*.zip' -o -name 'v*.json' \) -printf '%P|%s\n' 2>/dev/null"
    $lines = & ssh "${User}@${HostName}" "$findCmd" 2>$null
    if (-not $lines) {
        return $remote
    }
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed -notmatch '\|') { continue }
        $parts = $trimmed.Split('|', 2)
        if ($parts.Count -ne 2) { continue }
        $rel = $parts[0] -replace '\\', '/'
        if ($rel -match '^([^/]+)/(.+)$') {
            $remote[$rel] = [long]$parts[1]
        }
    }
    return $remote
}

Write-Host "Local packs : $LocalPacksDir"
Write-Host "Remote packs: $remoteTarget"
Write-Host "Fetching remote inventory..."
$localManifest = Get-LocalPackManifest -Root $LocalPacksDir
$remoteManifest = Get-RemotePackManifest -User $SshUser -HostName $SshHost -RemoteDir $RemotePacksDir

$toUpload = @()
$skippedSame = 0
$skippedSmaller = 0
$toUpgrade = 0

foreach ($entry in $localManifest.Values) {
    $rel = $entry.RelativePath
    if ($remoteManifest.ContainsKey($rel)) {
        $remoteSize = $remoteManifest[$rel]
        if ($remoteSize -eq $entry.SizeBytes) {
            $skippedSame++
            continue
        }
        if ($entry.SizeBytes -gt $remoteSize) {
            $entry | Add-Member -NotePropertyName UploadReason -NotePropertyValue "upgrade" -Force
            $entry | Add-Member -NotePropertyName RemoteSizeBytes -NotePropertyValue $remoteSize -Force
            $toUpload += $entry
            $toUpgrade++
            continue
        }
        Write-Warning "Skip $rel (remote $remoteSize bytes >= local $($entry.SizeBytes) bytes)"
        $skippedSmaller++
        continue
    }
    $entry | Add-Member -NotePropertyName UploadReason -NotePropertyValue "missing" -Force
    $toUpload += $entry
}

Write-Host ""
Write-Host "Local packs   : $($localManifest.Count)"
Write-Host "Remote packs  : $($remoteManifest.Count)"
Write-Host "Already synced: $skippedSame"
Write-Host "To upgrade    : $toUpgrade (local larger than remote)"
Write-Host "Skipped       : $skippedSmaller (remote same or larger)"
Write-Host "To upload     : $($toUpload.Count)"

if ($toUpload.Count -eq 0) {
    Write-Host "Nothing to upload."
} elseif ($DryRun) {
    Write-Host ""
    Write-Host "Dry run - would upload:"
    $toUpload | ForEach-Object {
        $sizeMb = [math]::Round($_.SizeBytes / 1MB, 2)
        $tag = if ($_.UploadReason -eq "upgrade") { "upgrade" } else { "new" }
        if ($_.UploadReason -eq "upgrade") {
            $remoteMb = [math]::Round($_.RemoteSizeBytes / 1MB, 2)
            Write-Host "  [$tag] $($_.RelativePath) ($remoteMb -> $sizeMb MB)"
        } else {
            Write-Host "  [$tag] $($_.RelativePath) ($sizeMb MB)"
        }
    }
} else {
    $uploaded = 0
    $failed = 0
    foreach ($entry in $toUpload) {
        $rel = $entry.RelativePath
        $code = $rel.Split('/')[0]
        $fileName = Split-Path $rel -Leaf
        $remoteDir = "$RemotePacksDir/$code"
        $sizeMb = [math]::Round($entry.SizeBytes / 1MB, 2)
        $action = if ($entry.UploadReason -eq "upgrade") { "Upgrading" } else { "Uploading" }
        Write-Host "$action $rel ($sizeMb MB)..."
        & ssh "${SshUser}@${SshHost}" "mkdir -p '$remoteDir'"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to create remote dir for $code"
            $failed++
            continue
        }
        if ($entry.UploadReason -eq "upgrade") {
            & ssh "${SshUser}@${SshHost}" "rm -f '${remoteDir}/${fileName}'"
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Failed to remove old remote file for $rel (try: sudo chown -R ${SshUser}:${SshUser} $RemotePacksDir)"
                $failed++
                continue
            }
        }
        & scp $entry.LocalPath "${SshUser}@${SshHost}:${remoteDir}/${fileName}"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Upload failed: $rel"
            $failed++
            continue
        }
        $uploaded++
    }
    Write-Host ""
    Write-Host "Uploaded: $uploaded  Failed: $failed"
    if ($failed -gt 0) {
        Write-Host "Re-run this script to retry only missing packs."
        exit 1
    }
}

# Remove stale majors (v2/v3/…) so the API only sees the shipping file (usually v1.zip).
if ($CleanOldVersions) {
    Write-Host ""
    Write-Host "Cleaning stale remote pack versions (keep only local shipping file per language)..."
    $keepByCode = @{}
    foreach ($entry in $localManifest.Values) {
        $keepByCode[$entry.Code] = $entry.FileName
    }
    $stale = @()
    foreach ($rel in $remoteManifest.Keys) {
        if ($rel -notmatch '^([^/]+)/(v[^/]+)$') { continue }
        $code = $Matches[1]
        $fileName = $Matches[2]
        if (-not $keepByCode.ContainsKey($code)) { continue }
        $keep = $keepByCode[$code]
        if ($fileName -ne $keep) {
            $stale += "$code/$fileName"
        }
    }
    # Also catch local-only languages after upload (refresh remote list lightly from keep map)
    foreach ($code in $keepByCode.Keys) {
        $keep = $keepByCode[$code]
        foreach ($major in 2..9) {
            $candidate = "$code/v$major.zip"
            if ($candidate -ne "$code/$keep" -and -not ($stale -contains $candidate)) {
                # Will rm -f even if missing
                $stale += $candidate
            }
        }
        if ($keep -eq "v1.zip") {
            foreach ($extra in @("v1.json", "v2.json", "v3.json", "v3.zip", "v2.zip")) {
                if ($extra -ne $keep -and -not ($stale -contains "$code/$extra")) {
                    $stale += "$code/$extra"
                }
            }
        }
    }
    $stale = $stale | Select-Object -Unique | Sort-Object
    Write-Host "Stale candidates: $($stale.Count)"
    if ($DryRun) {
        $stale | Select-Object -First 40 | ForEach-Object { Write-Host "  would delete $_" }
        if ($stale.Count -gt 40) { Write-Host "  ... +$($stale.Count - 40) more" }
    } else {
        $deleted = 0
        foreach ($rel in $stale) {
            $remotePath = "$RemotePacksDir/$rel"
            & ssh "${SshUser}@${SshHost}" "rm -f '$remotePath'"
            if ($LASTEXITCODE -eq 0) { $deleted++ }
        }
        Write-Host "Deleted/attempted stale remote packs: $deleted"
    }
}

if ($RestartApi -and -not $DryRun -and ($toUpload.Count -gt 0 -or $CleanOldVersions)) {
    Write-Host "Restarting cheradip-ailt..."
    & ssh "${SshUser}@${SshHost}" "sudo systemctl restart cheradip-ailt"
}
