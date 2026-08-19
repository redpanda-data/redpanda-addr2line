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
import xml.etree.ElementTree as ET

#
# Public S3 bucket hosting Redpanda release artifacts. Anonymously
# readable, so no credentials are required.
#
releases_url = os.getenv(
    "REDPANDA_RELEASES_URL", "https://vectorized-public.s3.us-west-2.amazonaws.com"
).rstrip("/")
releases_prefix = "releases/redpanda/"

#
# Directory used to store extracted Redpanda releases
#
download_dir = pathlib.Path(os.getenv("DOWNLOAD_DIR", "/mnt/redpanda"))
assert download_dir.is_dir(), f"download directory {download_dir} does not exist"

#
# How often (in minutes) to query for new releases
refresh_key = "SYNC_REFRESH_MINUTES"
refresh_seconds = 60 * int(os.getenv(refresh_key, 30))
assert refresh_seconds > 0, f"invalid refresh rate: {os.getenv(refresh_key)}"

#
# Minimum major version that will be considered when syncing
#
min_major_version = int(os.getenv("MIN_MAJOR_VERSION", 22))

#
# Supported Redpanda architectures to download. Keys are the directory
# names used on disk and in the app's public API; values are the arch
# suffix used in the release filename in the S3 bucket, which differs
# for arm ("arm" here vs. "arm64" in the object key).
#
supported_architectures = {"amd64": "amd64", "arm": "arm64"}

_s3_ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_all_versions():
    """
    List all Redpanda release versions published under releases/redpanda/
    in the public vectorized-public S3 bucket.
    """
    versions = []
    token = None
    with requests.Session() as sesh:
        while True:
            params = {
                "list-type": "2",
                "prefix": releases_prefix,
                "delimiter": "/",
            }
            if token:
                params["continuation-token"] = token
            with sesh.get(releases_url, params=params, timeout=60) as resp:
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                for cp in root.findall("s3:CommonPrefixes", _s3_ns):
                    prefix = cp.findtext("s3:Prefix", namespaces=_s3_ns)
                    versions.append(prefix[len(releases_prefix):].rstrip("/"))
                if root.findtext("s3:IsTruncated", namespaces=_s3_ns) != "true":
                    break
                token = root.findtext("s3:NextContinuationToken", namespaces=_s3_ns)
    return versions


def sync_packages():
    """
    List all Redpanda releases eligible to sync, across supported archs.
    """
    for version in list_all_versions():
        m = re.match(r"^(?P<major>\d{2})\.\d+\.\d{1,2}$", version)
        if not m:
            print(f"Skipping release with invalid version: {version}")
            continue
        if int(m.group("major")) < min_major_version:
            print(
                f"Skipping release {version} with major version < {min_major_version}"
            )
            continue

        for arch, s3_arch in supported_architectures.items():
            url = f"{releases_url}/{releases_prefix}{version}/redpanda-{version}-{s3_arch}.tar.gz"
            yield version, url, arch


def download_package(version, url, arch):
    """
    Downloads and extracts a Redpanda release into download directory.
    """
    path = download_dir / arch / version
    if path.is_dir():
        print(f"Skipping {version} at {path}: already downloaded")
        return

    print(f"Downloading {version} from {url}")
    try:
        resp = requests.get(url, stream=True, timeout=60)
    except requests.RequestException as e:
        print(f"Skipping {version} ({arch}): request failed: {e}")
        return

    f = tempfile.NamedTemporaryFile(delete=False)
    try:
        with resp:
            if resp.status_code == 404:
                # Not every version has every arch published (e.g. older
                # releases predating an architecture, or a partial upload
                # in progress).
                print(f"Skipping {version} ({arch}): not published at {url}")
                os.unlink(f.name)
                return
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                print(f"Skipping {version} ({arch}): {e}")
                os.unlink(f.name)
                return
            shutil.copyfileobj(resp.raw, f)
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
        ), f"Redpanda binary not found in extracted release {version} at location {redpanda.as_posix()}"
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
            for version, url, arch in sync_packages():
                download_package(version, url, arch)
            print(f"Refresh complete. Next refresh in {refresh_seconds} sec")
            stop.wait(refresh_seconds)

        except Exception:
            traceback.print_exc()
            print("Encountered exception. Trying refresh again in 5 minutes")
            stop.wait(300)

    print("Redpanda release synchronizer stopping")
