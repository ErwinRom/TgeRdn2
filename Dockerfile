# Obraz dodatku Home Assistant.
#
# Zero zaleznosci: tgerdn korzysta tylko z biblioteki standardowej Pythona,
# wiec obraz nie ma pip-a ani sekcji instalacyjnych - buduje sie w kilka
# sekund i nie ciagnie niczego z sieci poza samym interpreterem.

ARG BUILD_ARCH=amd64
FROM python:3.13-slim

LABEL io.hass.type="app" \
      io.hass.version="2.1.8" \
      io.hass.arch="${BUILD_ARCH}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY tgerdn/ /app/tgerdn/
COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

# Katalog z plikami JSON (mapowany z /config w dodatku).
VOLUME /config

CMD ["/app/run.sh"]
