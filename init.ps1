#python3 -m venv venv
#. ./venv/Scripts/Activate.ps1
$sep = [System.IO.Path]::PathSeparator
python3 -m pip install --upgrade pip setuptools wheel uv
python -m uv sync
$env:PYTHONPATH = "$( Get-Location )$sep$env:PYTHONPATH"
