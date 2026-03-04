# Import SQL dumps from C:\Users\sasha\Desktop\database into cheradip_cheradip (XAMPP MySQL)
# Usage: Run in PowerShell. Ensure XAMPP MySQL is running and mysql is in PATH or set $mysql below.

$ErrorActionPreference = "Continue"
$dbName = "cheradip_cheradip"
$user = "root"
$sourceDir = "C:\Users\sasha\Desktop\database"
$charset = "utf8mb4"

# Use mysql from PATH, or set full path for XAMPP
$mysql = "mysql"
if (-not (Get-Command $mysql -ErrorAction SilentlyContinue)) {
    $mysql = "C:\xampp\mysql\bin\mysql.exe"
}
if (-not (Test-Path $mysql) -and -not (Get-Command $mysql -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: mysql not found. Add XAMPP mysql to PATH or set `$mysql in this script."
    exit 1
}

if (-not (Test-Path $sourceDir)) {
    Write-Host "ERROR: Source folder not found: $sourceDir"
    exit 1
}

$files = @(
    "cheradip_country.sql",
    "cheradip_location.sql",
    "cheradip_banbeis.sql",
    "cheradip_institutes.sql",
    "cheradip_merit5.sql",
    "cheradip_merit6.sql",
    "cheradip_merit7.sql",
    "cheradip_recommend5.sql",
    "cheradip_recommend6.sql",
    "cheradip_vacancy5.sql",
    "cheradip_vacancy6.sql",
    "cheradip_vacancy7.sql",
    "cheradip_subject_translated.sql",
    "cheradip_token.sql"
)

Write-Host "Importing into database: $dbName (user: $user)"
Write-Host "Using charset: $charset (--force so CREATE errors are skipped and INSERT runs)"
Write-Host ""

foreach ($f in $files) {
    $path = Join-Path $sourceDir $f
    if (-not (Test-Path $path)) {
        Write-Host "SKIP (not found): $f"
        continue
    }
    Write-Host "Importing: $f ..."
    $proc = Start-Process -FilePath $mysql -ArgumentList "-u", $user, "--default-character-set=$charset", "--force", $dbName -PassThru -NoNewWindow -RedirectStandardInput $path -Wait
    if ($proc.ExitCode -eq 0) {
        Write-Host "  OK: $f"
    } else {
        Write-Host "  (exit code $($proc.ExitCode); --force so INSERT may still have run)"
    }
}

# cheradip_token.sql creates table cheradip_token; Django uses table name "tokens"
Write-Host ""
Write-Host "Copying cheradip_token -> tokens ..."
$copySql = "INSERT IGNORE INTO tokens (id, Token, Counter, Status, purpose, expires_at, created_at, updated_at) SELECT id, CAST(Token AS UNSIGNED), COALESCE(CAST(Counter AS CHAR), ''), Status, NULL, NULL, NOW(), NOW() FROM cheradip_token;"
$copySql | & $mysql -u $user --default-character-set=$charset $dbName 2>&1
# cheradip_merit7.sql dump uses table name cheradip_merit
Write-Host "Copying cheradip_merit -> cheradip_merit7 ..."
"INSERT IGNORE INTO cheradip_merit7 (id, Code, Name, Batch, Roll, Mark, Rank, SL, Subject) SELECT id, Code, Name, Batch, Roll, Mark, Rank, SL, Subject FROM cheradip_merit;" | & $mysql -u $user --default-character-set=$charset $dbName 2>&1
# cheradip_vacancy7.sql dump uses table name cheradip_vacancy
Write-Host "Copying cheradip_vacancy -> cheradip_vacancy7 ..."
"INSERT IGNORE INTO cheradip_vacancy7 (VPID, EIIN, Name, District, Thana, Designation, Subject, Vacancy, Type, Status) SELECT VPID, EIIN, Name, District, Thana, Designation, Subject, Vacancy, Type, Status FROM cheradip_vacancy;" | & $mysql -u $user --default-character-set=$charset $dbName 2>&1
Write-Host "Done."
Write-Host ""
Write-Host "If you see duplicate key or column errors, tables may already have data or different structure."
Write-Host "To start fresh for a table: TRUNCATE TABLE table_name; then re-run this script for that file."
