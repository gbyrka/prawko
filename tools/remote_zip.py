"""Index HTTPS ZIP archives and retrieve individual members by byte range."""

from hashlib import sha256
from http.client import IncompleteRead
import io
import re
import struct
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
import zlib


TAIL_SIZE = 4 * 1024 * 1024
MAX_MEDIA_SIZE = 128 * 1024 * 1024
LOCAL_HEADER = struct.Struct("<4s5H3I2H")


def read_range(url, requested, expected_total=None, version=None):
    for attempt in range(3):
        try:
            return _read_range(url, requested, expected_total, version)
        except HTTPError as error:
            if attempt == 2 or (error.code < 500 and error.code not in (408, 429)):
                raise
        except (URLError, OSError, IncompleteRead, EOFError):
            if attempt == 2:
                raise
        sleep(attempt + 1)


def _read_range(url, requested, expected_total, version):
    if urlsplit(url).scheme != "https":
        raise ValueError("Archiwum zdalne musi mieć adres HTTPS.")
    headers = {"Range": f"bytes={requested}", "Accept-Encoding": "identity"}
    if version:
        headers["If-Range"] = version
    with urlopen(Request(url, headers=headers), timeout=35) as response:
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
        if response.status != 206 or not match:
            raise ValueError("Serwer nie zwrócił zakresu bajtów. Archiwum mogło się zmienić.")
        start, end, total = map(int, match.groups())
        if expected_total is not None and total != expected_total:
            raise ValueError("Rozmiar zdalnego archiwum uległ zmianie.")
        if requested.startswith("-"):
            wanted = (max(0, total - int(requested[1:])), total - 1)
        else:
            wanted = tuple(map(int, requested.split("-", maxsplit=1)))
        length = end - start + 1
        if (start, end) != wanted or not 0 < length <= MAX_MEDIA_SIZE:
            raise ValueError("Serwer zwrócił nieprawidłowy fragment archiwum.")
        contents = response.read(length + 1)
        if len(contents) != length:
            raise EOFError("Niepełny fragment archiwum.")
        etag = response.headers.get("ETag", "")
        new_version = etag if etag and not etag.startswith("W/") else response.headers.get("Last-Modified")
        if version and new_version and new_version != version:
            raise ValueError("Wersja zdalnego archiwum uległa zmianie.")
        return contents, start, total, new_version


class ArchiveIndex(io.RawIOBase):
    def __init__(self, url):
        self.url = url
        self.tail, self.tail_offset, self.size, self.version = read_range(url, f"-{TAIL_SIZE}")
        self.position = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        start = (0, self.position, self.size)[whence]
        value = start + offset
        if value < 0:
            raise OSError("Negative seek")
        self.position = value
        return value

    def read(self, length=-1):
        start = self.position
        end = self.size if length < 0 else min(start + length, self.size)
        if start >= end:
            return b""
        if start >= self.tail_offset:
            contents = self.tail[start - self.tail_offset:end - self.tail_offset]
        else:
            contents, _, _, _ = read_range(self.url, f"{start}-{end - 1}", self.size, self.version)
        self.position = end
        return contents

    def entries(self):
        with ZipFile(self) as zip_file:
            entries = sorted(zip_file.infolist(), key=lambda entry: entry.header_offset)
            ends = [item.header_offset for item in entries[1:]] + [zip_file.start_dir]
            for info, end in zip(entries, ends):
                if not info.is_dir():
                    yield info, {
                        "url": self.url, "total": self.size, "version": self.version,
                        "start": info.header_offset, "end": end - 1, "filename": info.filename,
                        "packed": info.compress_size, "size": info.file_size, "crc": info.CRC,
                        "method": info.compress_type,
                    }


def media_key(entry):
    # Reuse the stored copy across releases when an unchanged member stays in the same archive.
    # The original CRC and size are checked again when bytes are fetched.
    identity = f'{entry["url"]}\n{entry["filename"]}\n{entry["crc"]}\n{entry["size"]}'
    return "remote-" + sha256(identity.encode()).hexdigest()


def fetch_member(entry):
    if entry["size"] > MAX_MEDIA_SIZE:
        raise ValueError("Plik multimedialny jest większy niż limit serwera.")
    block, _, _, _ = read_range(entry["url"], f'{entry["start"]}-{entry["end"]}',
                                 entry["total"], entry["version"])
    if len(block) < LOCAL_HEADER.size:
        raise ValueError("Brak nagłówka rekordu ZIP.")
    (magic, _, flags, method, _, _, _, _, _, name_len, extra_len) = LOCAL_HEADER.unpack_from(block)
    offset = LOCAL_HEADER.size + name_len + extra_len
    limit = offset + entry["packed"]
    if magic != b"PK\x03\x04" or flags & 1 or method != entry["method"] or limit > len(block):
        raise ValueError("Uszkodzony lub nieobsługiwany rekord ZIP.")
    packed = block[offset:limit]
    if method == ZIP_STORED:
        contents = packed
    elif method == ZIP_DEFLATED:
        decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        contents = decoder.decompress(packed, entry["size"] + 1)
        if not decoder.eof:
            raise ValueError("Niepełne dane skompresowanego pliku.")
    else:
        raise ValueError(f"Nieobsługiwana kompresja ZIP: {method}.")
    if len(contents) != entry["size"] or zlib.crc32(contents) != entry["crc"]:
        raise ValueError("Suma kontrolna pliku z ZIP nie zgadza się z katalogiem.")
    return contents
