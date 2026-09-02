# Stub PulsoWeb API for the documentation screenshot harness. Standard library
# only, so there is nothing to install and nothing to keep up to date.
FROM python:3.12-alpine
WORKDIR /srv
COPY server.py .
COPY payloads ./payloads
EXPOSE 8000
CMD ["python", "-u", "server.py"]
