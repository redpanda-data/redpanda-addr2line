## Run locally

If you have `docker-compose` installed then you can run the application locally
using the provided script (add `--docker` if not using `podman`):

```
./run-local.sh
```

once the application is running it can be accessed using a browser:

* https://localhost:8000/docs
* Username: admin
* Password: admin

## Production deployment

Configure with the following environment variables:

```
DOMAIN=
USERNAME=
PASSWORD='$2a$14$5xcXSjDxrwqSzh685qOZO.ltM.jpA90kNlpT9TfIZV4LLcvYPh3Si'
```

The standard 80/443 ports are used for http/https. The Caddy reverse proxy with
automatically set up SSL for the configured domain.

To configure the password compute the hash of the plaintext representation:

```
echo secret | docker run -i caddy:2.6.4-alpine caddy hash-password
```

Then set the output to the `PASSWORD` environment variable. Be sure to escape
the `$` in the hash or use single quotes.
