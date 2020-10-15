FROM debian:buster

EXPOSE 8000
ARG CALIBRE_UID=112

RUN apt update && apt -y install calibre sqlite3 python3 python3-pip zlib1g-dev libjpeg-dev locales
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
RUN useradd -ms /bin/bash -u ${CALIBRE_UID} -g www-data calibre

COPY . /var/www/calibre_webui
WORKDIR /var/www/calibre_webui

RUN pip3 install -r /var/www/calibre_webui/requirements.txt
