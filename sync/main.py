import contextlib
import os
import pathlib
import re
import requests
import shutil
import signal
import tarfile
import tempfile
import threading
import traceback

#
# Cloudsmith API key for listing and downloading releases
#
api_key = os.getenv("CLOUDSMITH_API_KEY", None)
assert api_key, "required api key not provided: set CLOUDSMITH_API_KEY"

#
# Directory used to store extracted Redpanda releases
#
download_dir = pathlib.Path(os.getenv("DOWNLOAD_DIR", "/mnt/redpanda"))
assert download_dir.is_dir(), f"download directory {download_dir} does not exist"

#
# How often (in minutes) to query for new releases
refresh_key = "CLOUDSMITH_REFRESH_MINUTES"
refresh_seconds = 60 * int(os.getenv(refresh_key, 30))
assert refresh_seconds > 0, "invalid refresh rate: {os.getenv(refresh_key)}"

#
# Minimum major version that will be considered when syncing
#
min_major_version = int(os.getenv("MIN_MAJOR_VERSION", 22))

#
# Supported Redpanda architectures to download
#
supported_architectures = {"amd64", "arm"}


@contextlib.contextmanager
def cloudsmith_session():
    """
    Build a cloudsmith api request sessions with configured api key.
    """
    with requests.Session() as sesh:
        sesh.headers.update(
            {
                "Accept": "*/*",
                "X-Api-Key": api_key,
            }
        )
        yield sesh


def list_all_packages(architecture):
    """
    Fetch all known Redpanda packages.
    """

    def package_iter(sesh):
        url = ("https://api.cloudsmith.io/v1/packages/redpanda/redpanda/?q=name:redpanda-{}+format:raw"
               .format(architecture))
        while url is not None:
            resp = sesh.get(url)
            resp.raise_for_status()
            yield from resp.json()
            link = resp.links.get("next", None)
            url = link.get("url", None) if link else None

    with cloudsmith_session() as sesh:
        return [p for p in package_iter(sesh)]


def sync_packages():
    """
    List all Redpanda packages eligible to sync.
    """

    for arch in supported_architectures:
        for pkg in list_all_packages(arch):
            name = pkg["name"]
            assert (
                    name == "redpanda-{}".format(arch)
            ), f"Query returned package with unsupported name: {name}"
            assert (
                    pkg["format"] == "raw"
            ), f"Query returned package with unsupported format: {pkg['format']}"

            version = pkg["version"]
            m = re.match(r"^(?P<major>\d{2})\.\d+\.\d{1,2}$", version)
            if not m:
                print(f"Skipping package {name} with invalid version: {version}")
                continue
            if int(m.group("major")) < min_major_version:
                print(
                    f"Skipping package {name} with major version {version} < {min_major_version}"
                )
                continue
            if not pkg["is_downloadable"] or not pkg["is_sync_completed"]:
                print(
                    f"Skipping package {name} not ready: d={pkg['is_downloadable']} s={pkg['is_sync_completed']}"
                )
                continue

        yield version, pkg["cdn_url"]


def download_package(version, url, arch):
    """
    Downloads and extracts a Redpanda release into download directory.
    """
    path = download_dir / arch / version
    if path.is_dir():
        print(f"Skipping {version} at {path}: already downloaded")
        return

    print(f"Downloading {version} from {url}")
    f = tempfile.NamedTemporaryFile(delete=False)
    try:
        with cloudsmith_session() as sesh:
            with sesh.get(url, stream=True) as s:
                shutil.copyfileobj(s.raw, f)
    except:
        os.unlink(f.name)
        raise
    finally:
        f.close()

    # create a temporary directory to unpack release into
    try:
        tdir = tempfile.mkdtemp()
    except:
        os.unlink(f.name)
        raise

    print(f"Extracting {version} at {f.name} into {tdir}")
    try:
        with tarfile.open(f.name) as tfile:
            tfile.extractall(path=tdir)
        redpanda = pathlib.Path(tdir) / "libexec" / "redpanda"
        assert (
            redpanda.is_file()
        ), "Redpanda binary not found in extracted release {version} at location {redpanda.as_posix()}"
        print(f"Moving extracted {version} from {tdir} to {path}")
        shutil.move(tdir, path)
    except:
        shutil.rmtree(tdir, ignore_errors=True)
        raise
    finally:
        os.unlink(f.name)


if __name__ == "__main__":
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    while not stop.is_set():
        try:
            for version, url in sync_packages():
                download_package(version, url)
            print(f"Refresh complete. Next refresh in {refresh_seconds} sec")
            stop.wait(refresh_seconds)

        except Exception:
            traceback.print_exc()
            print("Encountered exception. Trying refresh again in 5 minutes")
            stop.wait(300)

    print("Redpanda release synchronizer stopping")
