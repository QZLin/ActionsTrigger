#python3 -m venv venv
#. ./venv/Scripts/Activate.ps1
python3 -m pip install -r requirements.txt
$env:PYTHONPATH = "$( Get-Location )$([System.IO.Path]::PathSeparator)$env:PYTHONPATH"
