FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dbus-x11 \
        fluxbox \
        fonts-liberation \
        fonts-noto-cjk \
        nginx-light \
        novnc \
        python3-venv \
        websockify \
        x11vnc \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/entrust-venv
ENV PATH="/opt/entrust-venv/bin:${PATH}"

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir \
    -r /tmp/requirements.txt \
    playwright==1.60.0

COPY . /app
COPY nginx-novnc.conf /etc/nginx/nginx.conf
RUN chmod 0755 /app/docker-entrypoint.sh

EXPOSE 6080 8888

ENTRYPOINT ["/app/docker-entrypoint.sh"]
