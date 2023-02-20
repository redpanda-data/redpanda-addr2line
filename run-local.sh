#!/bin/bash

if [ -z "$CLOUDSMITH_API_KEY"]; then
    echo "Please set CLOUDSMITH_API_KEY environment variable"
    exit 1
fi

export DOMAIN=localhost
export HTTP_PORT=8001
export HTTPS_PORT=8000
export USERNAME=admin
export PASSWORD='$2a$14$5xcXSjDxrwqSzh685qOZO.ltM.jpA90kNlpT9TfIZV4LLcvYPh3Si'

if [[ "$@" != *"--docker"* ]]; then
    export DOCKER_HOST="unix:$XDG_RUNTIME_DIR/podman/podman.sock"
fi

docker-compose up
