FROM python:3.7-slim AS base

FROM base AS build
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    libyaml-dev
COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

# Comment out the line below if you want to use the Manhole module.
# You should only do this if you need to debug something on your IRC server.
# The docker image will be larger to support this.
#RUN pip install py-bcrypt

WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

ENTRYPOINT ["twistd", "-n", "txircd"]
