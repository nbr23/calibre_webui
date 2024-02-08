FROM alpine as bootstrap

RUN apk add --no-cache wget unzip

WORKDIR /build
COPY ./bootstrap.sh /build/
RUN ./bootstrap.sh

FROM ubuntu:22.04 as python_env

RUN apt update && DEBIAN_FRONTEND=noninteractive apt -y install gcc python3 python3-pip python3-venv

COPY requirements.txt .
RUN python3 -m venv /opt/python-env && PATH="/opt/python-env/bin:$PATH" pip3 install --no-cache-dir -r requirements.txt

FROM ubuntu:22.04

EXPOSE 8000
ARG CALIBRE_UID=112

RUN apt update && DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt -y --no-install-recommends install tzdata calibre sqlite3 python3 zlib1g-dev libjpeg-dev locales
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
RUN useradd -ms /bin/bash -u ${CALIBRE_UID} -g www-data calibre

RUN mkdir /etc/calibre_webui/ && chown ${CALIBRE_UID}:www-data /etc/calibre_webui/

WORKDIR /var/www/calibre_webui

COPY --from=python_env /opt/python-env /opt/python-env
ENV PATH="/opt/python-env/bin:$PATH"

COPY ./run_app.sh calibre_webui.ini calibre_webui.py ./
COPY ./calibre_webui ./calibre_webui

COPY --from=bootstrap /build/calibre_webui /var/www/calibre_webui/calibre_webui

COPY ./calibre_wrapper ./calibre_wrapper

CMD /var/www/calibre_webui/run_app.sh
