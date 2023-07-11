python3 -m venv venv
. ./venv/Scripts/Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "$( Get-Location );$env:PYTHONPATH"
