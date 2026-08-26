param(
    [ValidateSet("build", "status", "probe", "start", "stop", "restart", "install-task", "remove-task")]
    [string]$Command = "status"
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvFile = Join-Path $RootDir ".env"

function Import-DotEnv {
    if (-not (Test-Path $EnvFile)) { return }
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($key -and -not [Environment]::GetEnvironmentVariable($key, "Process")) {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

function Get-EnvValue([string]$Name, [string]$Default = "") {
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Resolve-ChatlogBin {
    $explicit = Get-EnvValue "CHATLOG_BIN"
    if ($explicit -and (Test-Path $explicit)) { return $explicit }

    $candidates = @(
        (Join-Path $RootDir ".local\chatlog\bin\chatlog.exe"),
        (Join-Path $RootDir ".local\wechat-local\chatlog_alpha\chatlog.exe"),
        (Join-Path $RootDir ".local\wechat-local\chatlog_alpha\chatlog-windows-amd64.exe"),
        (Join-Path $RootDir ".local\wechat-local\chatlog_alpha\chatlog-windows-arm64.exe"),
        (Join-Path $RootDir ".local\chatlog_0.0.31_windows_amd64\chatlog.exe"),
        (Join-Path $RootDir "chatlog_0.0.31_windows_amd64\chatlog.exe"),
        (Join-Path $RootDir "chatlog.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }

    $cmd = Get-Command "chatlog.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command "chatlog" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return ""
}

function Build-VendoredChatlog {
    $sourceDir = Join-Path $RootDir "third_party\chatlog"
    if (-not (Test-Path (Join-Path $sourceDir "go.mod"))) {
        throw "仓库内置 Chatlog 源码不存在：$sourceDir"
    }
    $go = Get-Command "go" -ErrorAction SilentlyContinue
    if (-not $go) { throw "需要安装 Go 1.24+ 才能编译仓库内置 Chatlog 源码。" }
    $outputDir = Join-Path $RootDir ".local\chatlog\bin"
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    $output = Join-Path $outputDir "chatlog.exe"
    $previousCgo = $env:CGO_ENABLED
    $env:CGO_ENABLED = if ($previousCgo) { $previousCgo } else { "1" }
    Push-Location $sourceDir
    try {
        & $go.Source build -trimpath `
            -ldflags "-s -w -X github.com/sjzar/chatlog/pkg/version.Version=vendored-bfb031f" `
            -o $output .\main.go
        if ($LASTEXITCODE -ne 0) { throw "Chatlog 编译失败，退出码：$LASTEXITCODE" }
    } finally {
        Pop-Location
        $env:CGO_ENABLED = $previousCgo
    }
    Write-Host "已从仓库内置源码构建 Chatlog：$output"
}

function Get-PortProcess([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    return Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
}

function Test-ChatlogHttp([string]$Base, [int]$Timeout = 5) {
    $url = $Base.TrimEnd("/") + "/api/v1/session"
    $started = Get-Date
    try {
        $resp = Invoke-WebRequest -Uri $url -TimeoutSec $Timeout -UseBasicParsing
        Write-Host ([pscustomobject]@{
            ok = $true
            url = $url
            status = [int]$resp.StatusCode
            latency_ms = [int]((Get-Date) - $started).TotalMilliseconds
        } | ConvertTo-Json -Compress)
        return $true
    } catch {
        Write-Host ([pscustomobject]@{
            ok = $false
            url = $url
            latency_ms = [int]((Get-Date) - $started).TotalMilliseconds
            error = $_.Exception.Message
        } | ConvertTo-Json -Compress)
        return $false
    }
}

function Assert-StartConfig {
    $bin = Resolve-ChatlogBin
    if (-not $bin) {
        Build-VendoredChatlog
        $bin = Resolve-ChatlogBin
    }
    if (-not $bin) {
        throw "仓库内置 Chatlog 编译后仍未找到 chatlog.exe"
    }
    $dataDir = Get-EnvValue "CHATLOG_DATA_DIR"
    $workDir = Get-EnvValue "CHATLOG_WORK_DIR" (Get-EnvValue "CHATLOG_DIR")
    if (-not $dataDir) { throw "缺少 CHATLOG_DATA_DIR，应指向 Windows 微信原始数据目录。" }
    if (-not $workDir) { throw "缺少 CHATLOG_WORK_DIR 或 CHATLOG_DIR，应指向 chatlog 解密工作目录。" }
    if (-not (Test-Path $dataDir)) { throw "CHATLOG_DATA_DIR 不存在：$dataDir" }
    New-Item -ItemType Directory -Force -Path $workDir | Out-Null
    return @{ bin = $bin; dataDir = $dataDir; workDir = $workDir }
}

function Start-ChatlogGray {
    $cfg = Assert-StartConfig
    $port = [int](Get-EnvValue "CHATLOG_GRAY_PORT" "5031")
    $existing = Get-PortProcess $port
    if ($existing) {
        Write-Host "chatlog 灰度服务已运行：pid=$($existing.Id) port=$port"
        return
    }

    $logDir = Get-EnvValue "CHATLOG_LOG_DIR" (Join-Path $RootDir "logs")
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $outLog = Get-EnvValue "CHATLOG_GRAY_LOG_FILE" (Join-Path $logDir "chatlog_5031.out.log")
    $errLog = Join-Path $logDir "chatlog_5031.err.log"

    $args = @(
        "server",
        "--addr", "127.0.0.1:$port",
        "--platform", (Get-EnvValue "CHATLOG_PLATFORM" "windows"),
        "--version", (Get-EnvValue "CHATLOG_VERSION" "4"),
        "--data-dir", $cfg.dataDir,
        "--work-dir", $cfg.workDir
    )
    $dataKey = Get-EnvValue "CHATLOG_DATA_KEY"
    $imgKey = Get-EnvValue "CHATLOG_IMG_KEY"
    if ($dataKey) { $args += @("--data-key", $dataKey) }
    if ($imgKey) { $args += @("--img-key", $imgKey) }
    if ((Get-EnvValue "CHATLOG_AUTO_DECRYPT" "0") -in @("1", "true", "TRUE")) { $args += "--auto-decrypt" }

    $proc = Start-Process -FilePath $cfg.bin -ArgumentList $args -WorkingDirectory $RootDir `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru -WindowStyle Hidden
    Write-Host "已启动 chatlog 灰度服务：pid=$($proc.Id) port=$port"

    $deadline = [int](Get-EnvValue "CHATLOG_STARTUP_TIMEOUT_SECONDS" "45")
    for ($i = 0; $i -lt $deadline; $i++) {
        Start-Sleep -Seconds 1
        if (Test-ChatlogHttp "http://127.0.0.1:$port" 3) { return }
        if ($proc.HasExited) { throw "chatlog 已退出，请查看日志：$outLog / $errLog" }
    }
    throw "chatlog 启动超时，请查看日志：$outLog / $errLog"
}

function Stop-ChatlogGray {
    $port = [int](Get-EnvValue "CHATLOG_GRAY_PORT" "5031")
    $proc = Get-PortProcess $port
    if (-not $proc) {
        Write-Host "chatlog 灰度服务未运行：port=$port"
        return
    }
    Stop-Process -Id $proc.Id -Force
    Write-Host "已停止 chatlog 灰度服务：pid=$($proc.Id)"
}

function Install-ChatlogTask {
    $taskName = Get-EnvValue "CHATLOG_TASK_NAME" "DeepseeChatlog5031"
    $script = Join-Path $RootDir "scripts\run_chatlog_windows.ps1"
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" start"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "Deepsee chatlog Windows sidecar" -Force | Out-Null
    Write-Host "已安装开机登录自启任务：$taskName"
}

function Remove-ChatlogTask {
    $taskName = Get-EnvValue "CHATLOG_TASK_NAME" "DeepseeChatlog5031"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已移除自启任务：$taskName"
}

Import-DotEnv

switch ($Command) {
    "build" { Build-VendoredChatlog }
    "probe" {
        $base = Get-EnvValue "CHATLOG_HTTP_BASE" "http://127.0.0.1:5030"
        Test-ChatlogHttp $base ([int](Get-EnvValue "CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS" "5")) | Out-Null
    }
    "status" {
        $primary = Get-EnvValue "CHATLOG_HTTP_BASE" "http://127.0.0.1:5030"
        $grayPort = [int](Get-EnvValue "CHATLOG_GRAY_PORT" "5031")
        Write-Host "primary_base=$primary"
        Test-ChatlogHttp $primary ([int](Get-EnvValue "CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS" "5")) | Out-Null
        Write-Host "gray_base=http://127.0.0.1:$grayPort"
        $proc = Get-PortProcess $grayPort
        Write-Host ("gray_pid=" + $(if ($proc) { $proc.Id } else { "" }))
        Test-ChatlogHttp "http://127.0.0.1:$grayPort" 5 | Out-Null
    }
    "start" { Start-ChatlogGray }
    "stop" { Stop-ChatlogGray }
    "restart" { Stop-ChatlogGray; Start-ChatlogGray }
    "install-task" { Install-ChatlogTask }
    "remove-task" { Remove-ChatlogTask }
}
