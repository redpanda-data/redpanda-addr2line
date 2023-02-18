from python:3.11-alpine

env PYTHONDONTWRITEBYTECODE 1
env PYTHONUNBUFFERED 1

workdir /usr/src/app

run pip install --upgrade pip
copy ./requirements.txt .
run pip install -r requirements.txt

copy main.py /usr/src/app
