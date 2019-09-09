FROM debian:buster

EXPOSE 8000

RUN apt update && apt -y install calibre sqlite3 python3 python3-pip zlib1g-dev libjpeg-dev
RUN useradd -ms /bin/bash -u 112 -g www-data calibre

COPY . /var/www/calibre_webui
WORKDIR /var/www/calibre_webui

RUN pip3 install -r /var/www/calibre_webui/requirements.txt
