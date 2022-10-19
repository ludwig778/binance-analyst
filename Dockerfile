FROM python:3.8-slim-buster

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && \
    apt-get install -y \
        curl \
        make \
	inotify-tools \
    && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PATH=$PATH:/root/.local/bin/

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install

ENV PYTHONUNBUFFERED 1

COPY . .

ENTRYPOINT ["make"]
