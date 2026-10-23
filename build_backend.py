"""Project-specific PEP 517 backend using only the Python standard library.

Build requirements are intentionally empty. This backend supports wheels and
source archives, not editable installs or arbitrary package layouts.
"""

import base64
import csv
import hashlib
import io
from pathlib import Path
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parent


def _project():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _metadata():
    project = _project()
    header = (f"Metadata-Version: 2.1\nName: {project['name']}\nVersion: {project['version']}\n"
              f"Summary: {project['description']}\nRequires-Python: {project['requires-python']}\n"
              "License: MIT\nDescription-Content-Type: text/markdown\n")
    for classifier in project["classifiers"]:
        header += f"Classifier: {classifier}\n"
    return (header + "\n" + (ROOT / project["readme"]).read_text(encoding="utf-8")).encode("utf-8")


def _dist_info():
    project = _project()
    return f"{project['name']}-{project['version']}.dist-info"


def _metadata_files():
    directory = _dist_info()
    return {f"{directory}/METADATA": _metadata(),
            f"{directory}/WHEEL": b"Wheel-Version: 1.0\nGenerator: tracebench-stdlib\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            f"{directory}/entry_points.txt": b"[console_scripts]\ntracebench = tracebench.cli:main\n",
            f"{directory}/LICENSE": (ROOT / "LICENSE").read_bytes()}


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    for name, data in _metadata_files().items():
        destination = Path(metadata_directory) / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return _dist_info()


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    project = _project()
    filename = f"{project['name']}-{project['version']}-py3-none-any.whl"
    contents = {str(path.relative_to(ROOT)).replace("\\", "/"): path.read_bytes()
                for path in sorted((ROOT / "tracebench").glob("*.py"))}
    contents.update(_metadata_files())
    records = io.StringIO(newline="")
    writer = csv.writer(records, lineterminator="\n")
    for name, data in sorted(contents.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
        writer.writerow([name, "sha256=" + digest, len(data)])
    record_name = f"{_dist_info()}/RECORD"
    writer.writerow([record_name, "", ""])
    contents[record_name] = records.getvalue().encode("utf-8")
    with zipfile.ZipFile(Path(wheel_directory) / filename, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return filename


def build_sdist(sdist_directory, config_settings=None):
    project = _project()
    stem = f"{project['name']}-{project['version']}"
    filename = stem + ".tar.gz"
    paths = [ROOT / name for name in ("pyproject.toml", "build_backend.py", "README.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md")]
    for directory in ("tracebench", "tests", "fixtures", "docs", "scripts"):
        paths.extend(p for p in sorted((ROOT / directory).rglob("*")) if p.is_file() and "__pycache__" not in p.parts)
    with tarfile.open(Path(sdist_directory) / filename, "w:gz") as archive:
        for path in paths:
            name = stem + "/" + path.relative_to(ROOT).as_posix()
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            with path.open("rb") as stream:
                archive.addfile(info, stream)
        data = _metadata()
        info = tarfile.TarInfo(stem + "/PKG-INFO")
        info.size, info.mode = len(data), 0o644
        archive.addfile(info, io.BytesIO(data))
    return filename
