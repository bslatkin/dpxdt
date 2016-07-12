rmdir sqlite_deploy /s /q
robocopy sqlite sqlite_deploy /e
cd sqlite_deploy

rem symlinks are replaced by text files, we should copy destination files manually
del /q /f dpxdt requirements.txt setup.py
robocopy ..\..\dpxdt dpxdt /e
copy ..\..\requirements.txt requirements.txt
copy ..\..\setup.py setup.py

python bootstrap.py
del /q /f bootstrap.py
cd ..
