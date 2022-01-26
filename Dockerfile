FROM ubuntu:rolling

EXPOSE 8000
ARG CALIBRE_UID=112

RUN apt update && DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt -y install tzdata calibre sqlite3 python3 python3-pip zlib1g-dev libjpeg-dev locales wget unzip
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
RUN userdel geoclue
RUN useradd -ms /bin/bash -u ${CALIBRE_UID} -g www-data calibre

RUN mkdir /etc/calibre_webui/ && chown ${CALIBRE_UID}:www-data /etc/calibre_webui/

WORKDIR /var/www/calibre_webui

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY ./run_app.sh calibre_webui.ini calibre_webui.py ./
COPY ./calibre_webui ./calibre_webui

COPY ./bootstrap.sh /var/www/calibre_webui
RUN ./bootstrap.sh && apt -y remove wget unzip

COPY ./calibre_wrapper ./calibre_wrapper

CMD /var/www/calibre_webui/run_app.sh
