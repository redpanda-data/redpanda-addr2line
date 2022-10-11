import os
import datetime
import subprocess
import logging.config
import requests
import shutil
import flask
import tempfile
import tarfile
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

CLOUDSMITH_API_KEY = os.getenv("CLOUDSMITH_API_KEY")
CLOUDSMITH_PACKAGES_URL = os.getenv(
    "CLOUDSMITH_PACKAGES_URL",
    "https://api.cloudsmith.io/v1/packages/vectorized/redpanda/?page_size=70",
)
CLOUDSMITH_REFRESH_SECONDS = os.getenv("CLOUDSMITH_REFRESH_SECONDS", 3600)
PACKAGE_CACHE_DIR = os.getenv("PACKAGE_CACHE_DIR", ".package_cache")
SEASTAR_ADDR2LINE_PATH = os.getenv(
    "SEASTAR_ADDR2LINE_PATH", "seastar/scripts/seastar-addr2line"
)

assert CLOUDSMITH_API_KEY, "CLOUDSMITH_API_KEY is required"

assert os.path.isfile(
    SEASTAR_ADDR2LINE_PATH
), f"Decoder not found at path: {SEASTAR_ADDR2LINE_PATH}"

if not os.path.isdir(PACKAGE_CACHE_DIR):
    os.mkdir(PACKAGE_CACHE_DIR)

logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["wsgi"]},
    }
)

app = flask.Flask(__name__)


@app.route("/")
def index():
    packages = filter(
        os.path.isdir,
        map(
            lambda d: os.path.join(PACKAGE_CACHE_DIR, d), os.listdir(PACKAGE_CACHE_DIR)
        ),
    )
    packages = os.listdir(PACKAGE_CACHE_DIR)
    app.logger.info(list(packages))
    return flask.render_template("index.html", packages=packages)


@app.route("/addr2line", methods=["POST"])
def addr2line():
    trace = flask.request.form["stacktrace"]
    package = flask.request.form["package"]
    bin_path = os.path.join(PACKAGE_CACHE_DIR, package, "libexec", "redpanda")
    app.logger.info(bin_path)
    app.logger.info([SEASTAR_ADDR2LINE_PATH, "-e", bin_path])
    decoded = subprocess.check_output(
        ["python", SEASTAR_ADDR2LINE_PATH, "-e", bin_path], text=True, input=trace
    )
    app.logger.info(decoded)
    return flask.render_template(
        "trace.html", package=package, trace=trace, decoded=decoded
    )


class package_manager:
    HEADERS = {
        "Accept": "*/*",
        "X-Api-Key": CLOUDSMITH_API_KEY,
    }

    @staticmethod
    def refresh():
        pkgs = package_manager._fetch_packages()
        for pkg in pkgs:
            path = package_manager._package_path(pkg)
            if os.path.isdir(path):
                app.logger.info(f"Skipping {path} which already exists")
                continue
            package_manager._download_package(pkg, path)

    @staticmethod
    def _fetch_packages():
        pkgs = requests.request(
            "GET", CLOUDSMITH_PACKAGES_URL, headers=package_manager.HEADERS
        ).json()
        pkgs = filter(lambda p: p["format"] == "raw", pkgs)
        return pkgs

    @staticmethod
    def _package_path(pkg):
        return os.path.join(PACKAGE_CACHE_DIR, pkg["files"][0]["filename"])

    @staticmethod
    def _download_package(pkg, path):
        url = pkg["files"][0]["cdn_url"]
        with tempfile.NamedTemporaryFile() as f:
            with requests.get(url, headers=package_manager.HEADERS, stream=True) as r:
                app.logger.info(f"Downloading {url}")
                shutil.copyfileobj(r.raw, f)
            dir = tempfile.mkdtemp()
            with tarfile.open(f.name) as t:
                def is_within_directory(directory, target):
                    
                    abs_directory = os.path.abspath(directory)
                    abs_target = os.path.abspath(target)
                
                    prefix = os.path.commonprefix([abs_directory, abs_target])
                    
                    return prefix == abs_directory
                
                def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                
                    for member in tar.getmembers():
                        member_path = os.path.join(path, member.name)
                        if not is_within_directory(path, member_path):
                            raise Exception("Attempted Path Traversal in Tar File")
                
                    tar.extractall(path, members, numeric_owner=numeric_owner) 
                    
                
                safe_extract(t, path=dir)
            shutil.move(dir, path)


scheduler = BackgroundScheduler(timezone=pytz.utc)

scheduler.add_job(
    package_manager.refresh,
    "interval",
    seconds=CLOUDSMITH_REFRESH_SECONDS,
    next_run_time=datetime.datetime.now(pytz.utc),
    max_instances=1,
)

scheduler.start()
