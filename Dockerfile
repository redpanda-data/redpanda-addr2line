FROM python:3.9-alpine
RUN apk add file binutils
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . /app
ADD https://raw.githubusercontent.com/scylladb/seastar/master/scripts/addr2line.py /app/seastar/scripts/
ADD https://raw.githubusercontent.com/scylladb/seastar/master/scripts/seastar-addr2line /app/seastar/scripts/
CMD ["flask", "run"]
