FROM python:3.8-slim-buster

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && \
    apt-get install -y \
        curl \
        make \
	inotify-tools \
    && \
    curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3 - && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PATH=$PATH:/root/.poetry/bin/

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install

COPY . .

ENTRYPOINT ["make"]
