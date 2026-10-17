"""Safe extraction of code files from an uploaded ZIP. Nothing is written to disk."""
import io
import posixpath
import zipfile

from app import config
from app.services.scanner import is_candidate

MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_TOTAL_UNCOMPRESSED = 40 * 1024 * 1024


class ArchiveError(Exception):
    pass


def read_zip(data: bytes) -> dict[str, str]:
    """Returns {path: text} for candidate code files. Rejects unsafe archives."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ArchiveError("That file is not a valid ZIP archive.") from None
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise ArchiveError(f"The archive has more than {MAX_ENTRIES} files.")
    if sum(i.file_size for i in infos) > MAX_TOTAL_UNCOMPRESSED:
        raise ArchiveError("The archive is too large once unpacked (limit 40 MB).")

    paths = []
    for i in infos:
        name = i.filename.replace("\\", "/")
        norm = posixpath.normpath(name)
        if name.startswith("/") or norm.startswith("..") or "/../" in f"/{norm}/":
            raise ArchiveError("The archive contains unsafe file paths.")
        if (i.external_attr >> 16) & 0o170000 == 0o120000:  # symlink
            continue
        paths.append((i, norm))

    # drop a single wrapping folder (e.g. repo-main/...)
    tops = {p.split("/")[0] for _, p in paths if "/" in p}
    strip = len(tops) == 1 and all("/" in p for _, p in paths)
    files: dict[str, str] = {}
    for info, p in paths:
        rel = p.split("/", 1)[1] if strip else p
        if not is_candidate(rel) or info.file_size > config.MAX_FILE_BYTES:
            continue
        try:
            files[rel] = zf.read(info).decode("utf-8")
        except UnicodeDecodeError:
            continue
    if not files:
        raise ArchiveError("No supported code files found (.py .js .jsx .ts .tsx .html .vue .svelte).")
    return files
