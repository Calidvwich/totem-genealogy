param(
    [switch]$CheckOnly
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
    return "'" + ($Value -replace "'", "'`"`"`'") + "'"
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

$ReloadFlag = @()
if ($Config.app.reload -eq $true) {
    $ReloadFlag = @("--reload")
}

$AppEnv = @(
    "cd",
    (Quote-Bash $Config.app.project_dir),
    "&&",
    "export TOTEM_USE_DEMO=" + (Quote-Bash $Config.app.use_demo),
    "&&",
    "export TOTEM_DATABASE=" + (Quote-Bash $Config.totem.database),
    "&&",
    "export TOTEM_USER=" + (Quote-Bash $Config.totem.user),
    "&&",
    "export TOTEM_PORT=" + (Quote-Bash $Config.totem.port)
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
    $HealthCheck = (Quote-Bash $Config.app.python) + " -c " + (Quote-Bash ("import urllib.request; urllib.request.urlopen('http://127.0.0.1:" + $Config.app.port + "', timeout=5).read(1)"))
    $StartWeb = @(
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
        "sleep 2;",
        "if $HealthCheck; then",
        "echo 'FastAPI is listening on port $($Config.app.port).';",
        "else",
        "echo 'FastAPI did not start. Recent log:';",
        "tail -80 $LogFile;",
        "exit 1;",
        "fi"
    )
    $AppCommand = (($AppEnv + @("&&") + $StartWeb) -join " ")
} else {
    $AppCommand = (($AppEnv + @("&&", "exec") + $UvicornCommand) -join " ")
}

$ExitCode = Invoke-WslBash -User $Config.wsl.app_user -Command $AppCommand
if ($ExitCode -eq 0 -and $Config.app.background -eq $true) {
    Write-Host "Startup finished. FastAPI is running in WSL background."
}
exit $ExitCode
