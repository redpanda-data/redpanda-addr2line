from python:3.11-alpine

run apk update && apk add file binutils llvm15

env PYTHONDONTWRITEBYTECODE 1
env PYTHONUNBUFFERED 1

workdir /usr/src/app

ADD https://raw.githubusercontent.com/scylladb/seastar/master/scripts/addr2line.py /usr/src/scripts/
ADD https://raw.githubusercontent.com/scylladb/seastar/master/scripts/seastar-addr2line /usr/src/scripts/

run pip install --upgrade pip
copy ./requirements.txt .
run pip install -r requirements.txt

copy main.py /usr/src/app
