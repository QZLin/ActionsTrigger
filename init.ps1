#python3 -m venv venv
#. ./venv/Scripts/Activate.ps1
$sep = [System.IO.Path]::PathSeparator
python3 -m pip install -r requirements.txt
$env:PYTHONPATH = "$( Get-Location )$sep$env:PYTHONPATH"
