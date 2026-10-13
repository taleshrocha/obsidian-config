# Atalho para Windows (PowerShell). Toda a lógica está em install.py.
# Uso: .\install.ps1 --vault C:\caminho\do\vault
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { & py -3 "$PSScriptRoot\install.py" @args; exit $LASTEXITCODE }
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) { & python "$PSScriptRoot\install.py" @args; exit $LASTEXITCODE }
Write-Error "Python 3 não encontrado. Instale em https://www.python.org/downloads/ e rode de novo."
exit 1
