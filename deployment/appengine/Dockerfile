# Dockerfile extending the generic Python image with application files for a
# single application.
FROM google/appengine-python27

ADD requirements.txt /app/

RUN echo 'deb http://gce_debian_mirror.storage.googleapis.com/ wheezy contrib non-free' >> /etc/apt/sources.list

RUN apt-get update -y

RUN apt-get install -y \
    curl \
    bzip2 \
    imagemagick \
    libfreetype6 \
    libfontconfig \
    ttf-mscorefonts-installer

RUN fc-cache -fv

# Based on https://github.com/ubermuda/docker-phantomjs/blob/master/Dockerfile
RUN curl -sSL \
    https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-1.9.8-linux-x86_64.tar.bz2 \
    | tar xj

RUN apt-get install -y \
    libmysqlclient-dev \
    python-dev

RUN pip install -r /app/requirements.txt

RUN easy_install -U distribute
RUN pip install GoogleAppEngineCloudStorageClient MySQL-python

ADD . /app
