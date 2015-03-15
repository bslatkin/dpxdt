# Dockerfile extending the generic Python image with application files for a
# single application.
FROM google/appengine-python27

RUN echo 'deb http://gce_debian_mirror.storage.googleapis.com/ wheezy contrib non-free' >> /etc/apt/sources.list

# RUN apt-get update && apt-get install -y \
#     imagemagick \
#     libfreetype6 \
#     libfontconfig \
#     ttf-mscorefonts-installer

# Rebuild the font cache
# RUN fc-cache -fv

ADD . /app
