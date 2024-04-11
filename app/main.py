import os
import pathlib
import re
import subprocess
from fastapi import FastAPI, HTTPException, Path, Body, status
from fastapi.responses import PlainTextResponse

#
# Maximum length of a stack trace that the API will accept
#
max_trace_length = int(os.getenv("MAX_TRACE_LEN", 2 ** 17))
assert max_trace_length > 0, f"Max trace length is daft: {max_trace_length}"

#
# Path to the seastar-addr2line script
#
addr2line = pathlib.Path(
    os.getenv("SEASTAR_ADDR2LINE_PATH", "/usr/src/scripts/seastar-addr2line")
)
assert addr2line.is_file(), f"seastar-addr2line tool {addr2line} does not exist"

#
# Directory containing extracted Redpanda releases
#
download_dir = pathlib.Path(os.getenv("DOWNLOAD_DIR", "/mnt/redpanda"))
assert download_dir.is_dir(), f"download directory {download_dir} does not exist"

#
# Supported Redpanda architectures to download
#
supported_architectures = {"amd64", "arm"}

app = FastAPI(redoc_url=None, debug=False)


@app.get("/versions", summary="Read supported Redpanda versions")
def versions():
    versions = []
    for arch in supported_architectures:
        tmp_versions = []
        arch_path = download_dir / arch
        for dir in arch_path.iterdir():
            if not dir.is_dir():
                continue
            if not re.match(r"^\d{2}\.\d\.\d{1,2}$", dir.name):
                continue
            tmp_versions.append(dir.name)
        versions.append((arch, tmp_versions))
    return versions


def redpanda_exec_path(arch, version):
    """
    Form the path to the redpanda binary for the given version.

    Raises a 404 exception if the resulting path does not point at a file.
    """
    redpanda = download_dir / arch / version / "libexec" / "redpanda"
    if not redpanda.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Redpanda version not found: {version}",
        )
    return redpanda


def decode_redpanda_backtrace(trace, arch, version):
    """
    Decode a backtrace against the specified version of Redpanda.
    """
    redpanda = redpanda_exec_path(arch, version).as_posix()
    args = f"python {addr2line} -a llvm15-addr2line -e {redpanda}"
    return subprocess.check_output(
        args.split(), stderr=subprocess.STDOUT, input=trace, text=True
    )


@app.post(
    "/backtrace/{version}",
    summary="Decode a backtrace from Redpanda",
    response_class=PlainTextResponse,
    response_description="Hey i'm a response desription",
)
def backtrace(
        version: str = Path(
            title="Redpanda version",
            default=...,
            regex=r"^\d{2}\.\d\.\d{1,2}$",
            example="22.3.11",
        ),
        arch: str = Path(
            title="Redpanda architecture",
            default=...,
            example="amd64",
        ),
        trace: str = Body(
            media_type="text/plain",
            min_length=1,
            max_length=max_trace_length,
            example="""Backtrace:
  0x5a3e146
  0x5aa1aa6
  /opt/redpanda/lib/libc.so.6+0x42abf
  0x5a5c27d
  0x5a5ff57
  0x5a5d329
  0x5980d81
  0x597ee9f
  0x1d4cfde
  0x5d7245d
  /opt/redpanda/lib/libc.so.6+0x2d58f
  /opt/redpanda/lib/libc.so.6+0x2d648
  0x1d472a4""",
        ),
):
    return decode_redpanda_backtrace(trace, arch, version)
