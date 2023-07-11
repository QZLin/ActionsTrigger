python3 -m venv venv
. venv/scripts/activate
pip install -r requirements.txt
$env:PYTHONPATH = "$( Get-Location );$env:PYTHONPATH"
