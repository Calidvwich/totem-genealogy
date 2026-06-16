param(
    [switch]$CheckOnly,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$DefaultConfig = Join-Path $ProjectRoot "config\startup\startup.json"
$LocalConfig = Join-Path $ProjectRoot "config\startup\startup.local.json"
$ConfigPath = $DefaultConfig

if (Test-Path $LocalConfig) {
    $ConfigPath = $LocalConfig
}

if (-not (Test-Path $ConfigPath)) {
    throw "Startup config not found: $ConfigPath"
}

$Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

function Quote-Bash {
    param([string]$Value)
    return "'" + ($Value -replace "'", "'\''") + "'"
}

function Bash-Env {
    param(
        [string]$Name,
        [string]$Value
    )
    return "export $Name=$((Quote-Bash $Value))"
}

function Join-WslPath {
    param(
        [string]$Base,
        [string]$Leaf
    )
    return $Base.TrimEnd("/") + "/" + $Leaf.TrimStart("/")
}

function Invoke-WslBash {
    param(
        [string]$User,
        [string]$Command
    )
    $Args = @("-d", $Config.wsl.distro)
    if ($User) {
        $Args += @("-u", $User)
    }
    $Args += @("--", "bash", "-lc", $Command)
    & wsl @Args | ForEach-Object { Write-Host $_ }
    $ExitCode = $LASTEXITCODE
    return [int]$ExitCode
}

function Test-WindowsHttp {
    param([string]$Port)
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 5
        return ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Get-WslConfigWarning {
    $WslConfig = Join-Path $env:USERPROFILE ".wslconfig"
    if (-not (Test-Path $WslConfig)) {
        return ""
    }
    $Text = Get-Content $WslConfig -Raw
    if ($Text -match "(?im)^\s*networkingMode\s*=\s*mirrored\s*$") {
        return @"
Detected networkingMode=mirrored in $WslConfig.
This WSL installation is currently warning that mirrored networking is ignored,
which can leave FastAPI reachable inside WSL but unreachable from Windows localhost.
Recommended fix in Windows PowerShell:
  copy "$WslConfig" "$WslConfig.bak"
  Set-Content "$WslConfig" "[wsl2]`nlocalhostForwarding=true"
  wsl --shutdown
Then run start-genealogy.bat again.
"@
    }
    return ""
}

function Build-TsqlArgs {
    $Tsql = Join-WslPath $Config.totem.bin_dir "tsql"
    $Parts = @(
        (Quote-Bash $Tsql),
        "-U",
        (Quote-Bash $Config.totem.user)
    )
    if ($Config.totem.port) {
        $Parts += @("-p", (Quote-Bash $Config.totem.port))
    }
    $Parts += @("-d", (Quote-Bash $Config.totem.database), "-c", (Quote-Bash "SELECT 1;"))
    return ($Parts -join " ")
}

Write-Host "Using startup config: $ConfigPath"
Write-Host "Starting TotemDB in WSL distro $($Config.wsl.distro)..."

$TotemCtl = Join-WslPath $Config.totem.bin_dir "totemctl"
$StartParts = @(
    (Quote-Bash $TotemCtl),
    "-D",
    (Quote-Bash $Config.totem.data_dir),
    "-l",
    (Quote-Bash $Config.totem.log_file)
)
if ($Config.totem.port) {
    $StartParts += @("-o", (Quote-Bash ("-p " + $Config.totem.port)))
}
$StartParts += "start"
$StartCommand = $StartParts -join " "

[void](Invoke-WslBash -User $Config.wsl.database_user -Command $StartCommand)

Write-Host "Checking TotemDB connection..."
$CheckCommand = Build-TsqlArgs
$CheckCode = Invoke-WslBash -User $Config.wsl.database_user -Command $CheckCommand
if ($CheckCode -ne 0) {
    Write-Host ""
    Write-Host "TotemDB connection failed. Check log in WSL:" -ForegroundColor Red
    Write-Host "tail -80 $($Config.totem.log_file)"
    exit $CheckCode
}

Write-Host "TotemDB is ready."

if ($CheckOnly) {
    Write-Host "CheckOnly finished. FastAPI was not started."
    exit 0
}

Write-Host "Starting FastAPI with uvicorn..."
Write-Host "Open http://localhost:$($Config.app.port) after startup."
if (-not $NoRestart) {
    Write-Host "Existing FastAPI process from the pid file will be restarted to avoid stale code."
}

$ReloadFlag = @()
if ($Config.app.reload -eq $true) {
    $ReloadFlag = @("--reload")
}

$AppEnv = @(
    "cd",
    (Quote-Bash $Config.app.project_dir),
    "&&",
    (Bash-Env "TOTEM_USE_DEMO" $Config.app.use_demo),
    "&&",
    (Bash-Env "TOTEM_DATABASE" $Config.totem.database),
    "&&",
    (Bash-Env "TOTEM_USER" $Config.totem.user),
    "&&",
    (Bash-Env "TOTEM_PORT" $Config.totem.port)
)

$UvicornCommand = @(
    (Quote-Bash $Config.app.python),
    "-m",
    "uvicorn",
    (Quote-Bash $Config.app.module),
    "--host",
    (Quote-Bash $Config.app.host),
    "--port",
    (Quote-Bash $Config.app.port)
) + $ReloadFlag

if ($Config.app.background -eq $true) {
    $PidFile = Quote-Bash $Config.app.pid_file
    $LogFile = Quote-Bash $Config.app.log_file
    $RestartFlag = if ($NoRestart) { "1" } else { "0" }
    $HealthCheck = (Quote-Bash $Config.app.python) + " -c " + (Quote-Bash ("import urllib.request; urllib.request.urlopen('http://127.0.0.1:" + $Config.app.port + "', timeout=5).read(1)"))
    $StartWeb = @(
        "if [ $RestartFlag -eq 0 ] && [ -f $PidFile ] && kill -0 `$(cat $PidFile) 2>/dev/null; then",
        "echo 'Stopping existing FastAPI PID' `$(cat $PidFile);",
        "kill `$(cat $PidFile) 2>/dev/null || true;",
        "for i in 1 2 3 4 5; do",
        "if ! kill -0 `$(cat $PidFile) 2>/dev/null; then break; fi;",
        "sleep 1;",
        "done;",
        "rm -f $PidFile;",
        "fi;",
        "if [ -f $PidFile ] && ! kill -0 `$(cat $PidFile) 2>/dev/null; then",
        "rm -f $PidFile;",
        "fi;",
        "if [ -f $PidFile ] && kill -0 `$(cat $PidFile) 2>/dev/null; then",
        "echo 'FastAPI already running with PID' `$(cat $PidFile);",
        "else",
        "nohup",
        ($UvicornCommand -join " "),
        ">",
        $LogFile,
        "2>&1",
        "&",
        "echo `$! > $PidFile;",
        "echo 'FastAPI started with PID' `$(cat $PidFile);",
        "fi;",
        "for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do",
        "if $HealthCheck >/dev/null 2>&1; then",
        "echo 'FastAPI is listening on port $($Config.app.port).';",
        "exit 0;",
        "fi;",
        "sleep 1;",
        "done;",
        "echo 'FastAPI did not start. Recent log:';",
        "tail -80 $LogFile;",
        "exit 1"
    )
    $AppCommand = (($AppEnv + @("&&") + $StartWeb) -join " ")
} else {
    $AppCommand = (($AppEnv + @("&&", "exec") + $UvicornCommand) -join " ")
}

$ExitCode = Invoke-WslBash -User $Config.wsl.app_user -Command $AppCommand
if ($ExitCode -eq 0 -and $Config.app.background -eq $true) {
    Write-Host "FastAPI is running in WSL background."
    Write-Host "Checking Windows localhost forwarding..."
    if (Test-WindowsHttp -Port $Config.app.port) {
        Write-Host "Windows can access http://localhost:$($Config.app.port)." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "FastAPI is reachable inside WSL, but Windows localhost:$($Config.app.port) is not reachable." -ForegroundColor Yellow
        Write-Host "This is usually a WSL NAT localhost forwarding issue, not a FastAPI failure."
        $WslConfigWarning = Get-WslConfigWarning
        if ($WslConfigWarning) {
            Write-Host ""
            Write-Host $WslConfigWarning -ForegroundColor Yellow
        }
        Write-Host "Try these commands in Windows, then run this script again:"
        Write-Host "  wsl --shutdown"
        Write-Host "  wsl -d $($Config.wsl.distro)"
        Write-Host ""
        Write-Host "You can also verify inside WSL:"
        Write-Host "  curl -I http://127.0.0.1:$($Config.app.port)/"
        Write-Host ""
        Write-Host "Recent FastAPI log:"
        Invoke-WslBash -User $Config.wsl.app_user -Command "tail -40 $LogFile" | Out-Null
        exit 2
    }
}
exit $ExitCode
