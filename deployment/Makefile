all:
	# Do nothing. You probably don't want both.

clean:
	rm -Rf appengine_deploy sqlite_deploy

appengine_deploy:
	rm -Rf appengine_deploy
	cp -R -L appengine appengine_deploy
	python -c \
	    "from dpxdt.server import app; \
	     app.jinja_env.compile_templates( \
	         './appengine_deploy/templates_compiled.zip')"

sqlite_deploy:
	rm -Rf sqlite_deploy
	cp -R -L sqlite sqlite_deploy
	cd sqlite_deploy && ./bootstrap.py
