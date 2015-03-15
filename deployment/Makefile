all:

clean:
	rm -Rf appengine_deploy

combined_vm:
	rm -Rf appengine_deploy
	cp -R -L appengine appengine_deploy
	python -c \
	    "from dpxdt.server import app; \
	     app.jinja_env.compile_templates( \
	         './appengine_deploy/templates_compiled.zip')"
	echo "- ^(.*/)?lib/jinja2(/.*)?" >> appengine_deploy/api_server.yaml
