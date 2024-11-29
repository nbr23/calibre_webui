ARG UBUNTU_VERSION=24.10
FROM alpine AS bootstrap

RUN apk add --no-cache wget unzip

WORKDIR /build
COPY ./bootstrap.sh /build/
RUN ./bootstrap.sh

FROM python:3.12-slim AS python_env
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python3 -m venv /opt/python-env && PATH="/opt/python-env/bin:$PATH" pip3 install --no-cache-dir -r requirements.txt

FROM ubuntu:${UBUNTU_VERSION}

EXPOSE 8000
ARG CALIBRE_UID=112

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
RUN apt update \
  && apt -y --no-install-recommends install tzdata calibre locales \
  && apt clean \ \
  && rm -rf /var/lib/apt/lists/* \
  && sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen en_US.UTF-8 \
  && useradd -ms /bin/bash -u ${CALIBRE_UID} -g www-data calibre \
  && mkdir /etc/calibre_webui/ && chown ${CALIBRE_UID}:www-data /etc/calibre_webui/

WORKDIR /var/www/calibre_webui

COPY --from=bootstrap /build/calibre_webui /var/www/calibre_webui/calibre_webui
COPY --from=python_env /opt/python-env /opt/python-env
ENV PATH="/opt/python-env/bin:$PATH"

COPY ./run_app.sh calibre_webui.ini calibre_webui.py ./
COPY ./calibre_webui ./calibre_webui


COPY ./calibre_wrapper ./calibre_wrapper

CMD ["/var/www/calibre_webui/run_app.sh"]
