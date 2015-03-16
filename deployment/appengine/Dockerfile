# Dockerfile extending the generic Python image with application files for a
# single application.
FROM google/appengine-python27

RUN echo 'deb http://gce_debian_mirror.storage.googleapis.com/ wheezy contrib non-free' >> /etc/apt/sources.list

RUN apt-get update -y && \
    apt-get install -y \
    libmysqlclient-dev \
    python-dev

RUN easy_install -U distribute
ADD requirements.txt /app/
RUN pip install -r requirements.txt

# RUN apt-get install -y \
#    imagemagick \
#    libfreetype6 \
#    libfontconfig \
#    ttf-mscorefonts-installer \
#    && fc-cache -fv

ADD . /app
