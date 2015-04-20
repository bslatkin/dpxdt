all:

clean:
	rm -Rf appengine_deploy

appengine_deploy:
	rm -Rf appengine_deploy
	cp -R -L appengine appengine_deploy
	python -c \
	    "from dpxdt.server import app; \
	     app.jinja_env.compile_templates( \
	         './appengine_deploy/templates_compiled.zip')"
