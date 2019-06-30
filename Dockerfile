FROM python:3.7-stretch

EXPOSE 8000

RUN apt update && apt -y install calibre sqlite3
RUN useradd -ms /bin/bash -g www-data calibre

COPY . /var/www/calibre_webui
WORKDIR /var/www/calibre_webui

RUN pip3 install -r /var/www/calibre_webui/requirements.txt
