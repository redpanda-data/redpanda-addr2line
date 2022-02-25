Obtain a cloudsmith.com API key.

Build the docker image.

```sh
docker build -t redpanda-addr2line .
```

Run the application.

```
docker run \
  -v ${PWD}/.package_cache:/app/.package_cache:z \
  -e FLASK_RUN_HOST=0.0.0.0 \
  -e FLASK_RUN_PORT=5000 \
  -e CLOUDSMITH_API_KEY= \
  -p 5000:5000
  redpanda-addr2line
```

Load http://localhost:5000 in a browser. Initially no packages will be shown
because they haven't been downloaded. This process runs once when the
application starts, and then again every hour to download new packages.
