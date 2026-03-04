@echo off
REM Import SQL from C:\Users\sasha\Desktop\database into cheradip_cheradip (XAMPP: root, no password)
set DB=cheradip_cheradip
set USER=root
set DIR=C:\Users\sasha\Desktop\database
set MYSQL=mysql
if not exist "C:\xampp\mysql\bin\mysql.exe" goto :check_path
set MYSQL=C:\xampp\mysql\bin\mysql.exe
:check_path
if not exist "%DIR%" (echo ERROR: Folder not found: %DIR% & exit /b 1)

echo Importing into %DB% ...
set CHARSET=utf8mb4

for %%F in ("%DIR%\cheradip_country.sql" "%DIR%\cheradip_location.sql" "%DIR%\cheradip_banbeis.sql" "%DIR%\cheradip_institutes.sql" "%DIR%\cheradip_merit5.sql" "%DIR%\cheradip_merit6.sql" "%DIR%\cheradip_merit7.sql" "%DIR%\cheradip_recommend5.sql" "%DIR%\cheradip_recommend6.sql" "%DIR%\cheradip_vacancy5.sql" "%DIR%\cheradip_vacancy6.sql" "%DIR%\cheradip_vacancy7.sql" "%DIR%\cheradip_subject_translated.sql" "%DIR%\cheradip_token.sql") do (
  if exist %%F (
    echo Importing %%F ...
    "%MYSQL%" -u %USER% --default-character-set=%CHARSET% --force %DB% < "%%F"
  )
)

echo Copying cheradip_token -^> tokens ...
"%MYSQL%" -u %USER% --default-character-set=%CHARSET% %DB% -e "INSERT IGNORE INTO tokens (id, Token, Counter, Status, purpose, expires_at, created_at, updated_at) SELECT id, CAST(Token AS UNSIGNED), COALESCE(CAST(Counter AS CHAR), ''), Status, NULL, NULL, NOW(), NOW() FROM cheradip_token;"
echo Copying cheradip_merit -^> cheradip_merit7 (dump uses wrong table name) ...
"%MYSQL%" -u %USER% --default-character-set=%CHARSET% %DB% -e "INSERT IGNORE INTO cheradip_merit7 (id, Code, Name, Batch, Roll, Mark, Rank, SL, Subject) SELECT id, Code, Name, Batch, Roll, Mark, Rank, SL, Subject FROM cheradip_merit;"
echo Copying cheradip_vacancy -^> cheradip_vacancy7 (dump uses wrong table name) ...
"%MYSQL%" -u %USER% --default-character-set=%CHARSET% %DB% -e "INSERT IGNORE INTO cheradip_vacancy7 (VPID, EIIN, Name, District, Thana, Designation, Subject, Vacancy, Type, Status) SELECT VPID, EIIN, Name, District, Thana, Designation, Subject, Vacancy, Type, Status FROM cheradip_vacancy;"
echo Done.
