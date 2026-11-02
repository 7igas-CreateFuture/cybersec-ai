$ErrorActionPreference='Stop'
$taskFile=Join-Path (Split-Path $PSScriptRoot -Parent) 'start.ps1'
$taskParseErrors=$null; $taskTokens=$null
$taskAst=[System.Management.Automation.Language.Parser]::ParseFile($taskFile,[ref]$taskTokens,[ref]$taskParseErrors)
if($taskParseErrors.Count){throw 'PowerShell syntax errors'}
$taskTry=@($taskAst.EndBlock.Statements | Where-Object {$_ -is [System.Management.Automation.Language.TryStatementAst]})[-1]
$taskBody=[scriptblock]::Create($taskTry.Extent.Text)
function Test-Path {param($LiteralPath) return $true}
function Test-LocalListener {param($Port) return $script:taskListening}
function Start-Sleep {param($Milliseconds)}
function Start-Process {param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle) $script:taskStarts++}
function Get-LocalJson {
 param($Url)
 if($Url -like '*11434*'){return @{version='test'}}
 if($script:taskHealthQueue.Count -gt 1){return $script:taskHealthQueue.Dequeue()}
 return $script:taskHealthQueue.Peek()
}
$taskOld=@{service='local-ai-assistant';protocol=2}
$taskNew=@{service='local-ai-assistant';protocol=2;cybersec_profile_version=1}
$taskCases=@(
 @{name='old_process_rejected';health=@($taskOld);listening=$true;error=$true;starts=0},
 @{name='matching_process_reused';health=@($taskNew);listening=$true;error=$false;starts=0},
 @{name='new_process_verified';health=@(@{},$taskNew);listening=$false;error=$false;starts=1},
 @{name='started_old_process_never_ready';health=@(@{},$taskOld);listening=$false;error=$true;starts=1}
)
foreach($taskCase in $taskCases){
 $script:taskHealthQueue=[System.Collections.Generic.Queue[object]]::new()
 foreach($taskItem in $taskCase.health){$script:taskHealthQueue.Enqueue($taskItem)}
 $script:taskListening=$taskCase.listening;$script:taskStarts=0
 $taskMutex=[pscustomobject]@{}
 $taskMutex | Add-Member ScriptMethod WaitOne {param($n) return $true}
 $taskMutex | Add-Member ScriptMethod ReleaseMutex {}
 $taskMutex | Add-Member ScriptMethod Dispose {}
 $taskAcquired=$false;$NoBrowser=$true;$taskPython='stub';$taskFailed=$false;$taskResult=@()
 try{$taskResult=@(& $taskBody)}catch{$taskFailed=$true}
 if($taskFailed -ne $taskCase.error -or $script:taskStarts -ne $taskCase.starts){throw "Failed: $($taskCase.name)"}
 if($taskCase.error -and $taskResult.Count){throw 'Rejected startup emitted ready output'}
 if(-not $taskCase.error -and $taskResult.Count -ne 1){throw 'Successful startup omitted ready output'}
 Write-Output "PASS $($taskCase.name)"
}
Write-Output '4 PowerShell startup behavior checks passed; all network/process actions stubbed.'
