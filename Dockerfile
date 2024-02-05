FROM python:3.10

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY . .
RUN apt-get update \
    && apt-get install -y \
        software-properties-common \
    && apt-get update \
    && apt-get install -y \
        wkhtmltopdf
RUN pip install --upgrade pip
RUN pip install --upgrade -r requirements.txt