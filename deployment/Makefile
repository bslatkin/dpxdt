IP_ADDRESS = $(shell python -c \
	'import socket; print socket.gethostbyname(socket.gethostname())')

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
	echo "- ^(.*/)?lib/jinja2(/.*)?" >> appengine_deploy/api_server.yaml
	sed -i '' 's/HOSTNAME/$(IP_ADDRESS)/g' appengine_deploy/combined_vm.yaml
