call Scripts/activate.bat
pip install -r requirements.txt
pip install -e .

set YOURAPPLICATION_SETTINGS=../../settings.cfg
set SQLITE_PRODUCTION=Yes

dpxdt_server --flagfile=flags.cfg
