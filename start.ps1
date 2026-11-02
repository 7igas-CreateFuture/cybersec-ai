param([switch]$NoBrowser, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
if ($CheckOnly) {
    Write-Output 'START_WRAPPER_OK - no services were stopped or started.'
    return
}
$taskPython = $env:LOCAL_AI_PYTHON
if (-not $taskPython) {
    $taskPythonCommand = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $taskPythonCommand) { $taskPythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue }
    if ($taskPythonCommand) { $taskPython = $taskPythonCommand.Source }
}
if (-not $taskPython) { throw 'Python not found. Set LOCAL_AI_PYTHON or add Python to PATH.' }
$taskOllamaApp = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama app.exe'
$taskMutex = [System.Threading.Mutex]::new($false, 'Local\CompanyLocalAIStartup')
$taskAcquired = $false
function Test-LocalListener([int]$Port) {
    $taskTcp = [System.Net.Sockets.TcpClient]::new()
    try { $taskConnect = $taskTcp.ConnectAsync('127.0.0.1', $Port); return ($taskConnect.Wait(500) -and $taskTcp.Connected) }
    catch { return $false } finally { $taskTcp.Dispose() }
}
function Get-LocalJson([string]$Url) {
    # Explicitly bypass system proxies for loopback health probes.
    $taskRequest = [System.Net.HttpWebRequest]::Create($Url)
    $taskRequest.Proxy = $null; $taskRequest.Timeout = 2000
    try {
        $taskResponse = $taskRequest.GetResponse()
        try { $taskReader = [System.IO.StreamReader]::new($taskResponse.GetResponseStream()); try { return ($taskReader.ReadToEnd() | ConvertFrom-Json) } finally { $taskReader.Dispose() } }
        finally { $taskResponse.Dispose() }
    } catch { return $null }
}
try {
    try { $taskAcquired = $taskMutex.WaitOne(30000) } catch [System.Threading.AbandonedMutexException] { $taskAcquired = $true }
    if (-not $taskAcquired) { throw '另一个启动操作仍在进行，请稍后再试。' }
    if (-not (Test-Path -LiteralPath $taskPython)) { throw '找不到 Python 运行环境，请重新配置助手。' }
    $taskModel = Get-LocalJson 'http://127.0.0.1:11434/api/version'
    if (-not $taskModel.version) {
        if (Test-LocalListener 11434) { throw '11434 已有程序监听，但健康检查暂未通过。没有启动第二个 Ollama，请等待或检查现有服务。' }
        $taskApp = Get-Process -Name 'ollama app' -ErrorAction SilentlyContinue
        if (-not $taskApp) {
            if (-not (Test-Path -LiteralPath $taskOllamaApp)) { throw '找不到 Ollama 应用。' }
            $env:OLLAMA_HOST = '127.0.0.1:11434'
            $env:OLLAMA_NO_CLOUD = '1'
            $env:NO_PROXY = 'localhost,127.0.0.1'
            # Ollama's own app is the sole owner of starting/restarting its server.
            # Never launch a competing "ollama serve" process here.
            Start-Process -FilePath $taskOllamaApp -WindowStyle Hidden
        }
        for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
            Start-Sleep -Milliseconds 1000
            $taskModel = Get-LocalJson 'http://127.0.0.1:11434/api/version'
            if ($taskModel.version) { break }
        }
        if (-not $taskModel.version) { throw 'Ollama 仍未就绪。没有启动重复服务；请检查 Ollama 的更新或错误提示。' }
    }
    $taskWeb = Get-LocalJson 'http://127.0.0.1:18765/health'
    if ($taskWeb.service -ne 'local-ai-assistant' -or $taskWeb.protocol -ne 2 -or $taskWeb.cybersec_profile_version -ne 1) {
        if (Test-LocalListener 18765) { throw '18765 被旧版助手或其他程序占用。没有启动重复助手，请先完成受控重启。' }
        $taskScript = Join-Path $PSScriptRoot 'local_server.py'
        Start-Process -FilePath $taskPython -ArgumentList @(('"' + $taskScript + '"'), '--no-browser') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
        for ($taskAttempt = 0; $taskAttempt -lt 15; $taskAttempt++) {
            Start-Sleep -Milliseconds 300
            $taskWeb = Get-LocalJson 'http://127.0.0.1:18765/health'
            if ($taskWeb.service -eq 'local-ai-assistant' -and $taskWeb.protocol -eq 2 -and $taskWeb.cybersec_profile_version -eq 1) { break }
        }
        if ($taskWeb.service -ne 'local-ai-assistant' -or $taskWeb.protocol -ne 2 -or $taskWeb.cybersec_profile_version -ne 1) { throw '本地页面服务未加载当前 CyberSec 配置，请检查实际运行版本。' }
    }
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:18765/' }
    Write-Output '本地助手已就绪（复用已有服务，不重复占用端口）。'
} finally {
    if ($taskAcquired) { $taskMutex.ReleaseMutex() }
    $taskMutex.Dispose()
}
