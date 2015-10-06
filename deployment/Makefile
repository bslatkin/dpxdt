all:

clean:
	rm -Rf sqlite_deploy

sqlite_deploy:
	rm -Rf sqlite_deploy
	cp -R -L sqlite sqlite_deploy
	cd sqlite_deploy && ./bootstrap.py
	rm sqlite_deploy/bootstrap.py
