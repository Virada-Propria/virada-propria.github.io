param(
    [ValidateSet('testar', 'simular', 'exemplo', 'preview')]
    [string]$Acao = 'testar',
    [string]$Zip,
    [string]$PythonExe,
    [string]$Run,
    [string]$Revisoes,
    [switch]$Browser,
    [switch]$Online,
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
if (-not $PythonExe) {
    $PythonExe = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw 'Python não encontrado. Informe -PythonExe com o caminho de um Python 3.10+.'
}
switch ($Acao) {
    'testar' { & $PythonExe -X utf8 -B -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -v }
    'simular' {
        if (-not $Zip) { throw 'Informe -Zip com o caminho do lote.' }
        $taskArgs = @($Zip, '--simular')
        if ($Browser) { $taskArgs += '--browser' }
        if ($Online) { $taskArgs += '--online' }
        if ($Revisoes) { $taskArgs += @('--revisoes', $Revisoes) }
        & $PythonExe -X utf8 -B (Join-Path $PSScriptRoot 'automacao/importar.py') @taskArgs
    }
    'exemplo' {
        $taskArgs = @()
        if ($Browser) { $taskArgs += '--browser' }
        & $PythonExe -X utf8 -B (Join-Path $PSScriptRoot 'exemplos/gerar_lotes.py') @taskArgs
    }
    'preview' {
        if (-not $Run) { throw 'Informe -Run com o diretório isolado retornado pela simulação.' }
        & $PythonExe -X utf8 -B (Join-Path $PSScriptRoot 'automacao/preview.py') $Run --port $Port
    }
}
exit $LASTEXITCODE
