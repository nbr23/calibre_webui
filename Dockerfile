ARG UBUNTU_VERSION=25.10
FROM alpine AS bootstrap

RUN apk add --no-cache wget unzip

WORKDIR /build
COPY ./bootstrap.sh /build/
RUN ./bootstrap.sh


FROM ubuntu:${UBUNTU_VERSION} AS python_env
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/python-env/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
COPY requirements.txt .

RUN apt update && \
    apt install -y --no-install-recommends python3 python3-pip python3-dev g++ && \
    uv venv /opt/python-env && \
    uv pip install --no-cache-dir -r requirements.txt && \
    apt purge -y python3-dev g++ && \
    apt autoremove -y && \
    apt clean && \
    rm -rf /var/lib/apt/lists/*

FROM ubuntu:${UBUNTU_VERSION}

EXPOSE 8000
ARG CALIBRE_UID=112

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PATH="/opt/python-env/bin:$PATH"

RUN apt update \
  && apt -y --no-install-recommends install python3 tzdata calibre locales \
  && apt clean \
  && rm -rf /var/lib/apt/lists/* \
  && sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen en_US.UTF-8 \
  && useradd -ms /bin/bash -u ${CALIBRE_UID} -g www-data calibre \
  && mkdir /etc/calibre_webui/ && chown ${CALIBRE_UID}:www-data /etc/calibre_webui/

WORKDIR /var/www/calibre_webui

COPY --from=python_env /opt/python-env /opt/python-env
COPY --from=bootstrap /build/calibre_webui /var/www/calibre_webui/calibre_webui

COPY ./run_app.sh calibre_webui.ini calibre_webui.py ./
COPY ./calibre_webui ./calibre_webui


COPY ./calibre_wrapper ./calibre_wrapper

CMD ["/var/www/calibre_webui/run_app.sh"]
