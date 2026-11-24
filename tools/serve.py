#!/usr/bin/env python3
"""Serve the local app and cache media fetched from the official archives."""

import argparse
from http.client import IncompleteRead
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
from subprocess import CalledProcessError
import threading
import zlib
from urllib.parse import urlsplit

from import_catalog import prepare_contents
from remote_zip import fetch_member


ASSET_NAME = re.compile(r"(?:remote-)?[a-f0-9]{64}(?:-v[12](?:-repaired)?)?\.(?:mp4|jpg|png|gif|webp)")
HTTP_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class MediaCache:
    def __init__(self, public):
        self.public = public
        self.assets = {}
        self.index_files = ()
        self.index_lock = threading.Lock()
        self.downloads = threading.Semaphore(4)
        self.locks = [threading.Lock() for _ in range(64)]

    def entry(self, filename):
        with self.index_lock:
            manifests = tuple(sorted((self.public / "data").glob("media-index-*.json"),
                                     key=lambda path: (path.stat().st_mtime_ns, path.name)))
            if self.index_files != manifests:
                assets = {}
                for path in manifests:
                    assets.update(json.loads(path.read_text(encoding="utf-8")))
                self.assets = assets
                self.index_files = manifests
            return self.assets.get(filename)

    def get(self, filename):
        path = self.public / "media" / filename
        if path.is_file():
            return path
        entry = self.entry(filename) if filename.startswith("remote-") else None
        if entry is None:
            return None
        lock = self.locks[hash(filename) % len(self.locks)]
        with lock:
            if not path.is_file():
                with self.downloads:
                    contents = fetch_member(entry)
                    cached = prepare_contents(contents, entry["filename"], path.parent)
                    try:
                        os.link(path.parent / cached["file"], path)
                    except FileExistsError:
                        pass
        return path


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, cache, **kwargs):
        self.cache = cache
        super().__init__(*args, directory=cache.public, **kwargs)

    def send_head(self):
        self.media_remaining = None
        path = urlsplit(self.path).path
        if not path.startswith("/media/"):
            return super().send_head()
        filename = path.removeprefix("/media/")
        if not ASSET_NAME.fullmatch(filename):
            self.send_error(404)
            return None
        try:
            local = self.cache.get(filename)
            if local is None:
                self.send_error(404)
                return None
            stream = local.open("rb")
        except (ValueError, OSError, EOFError, IncompleteRead, CalledProcessError, zlib.error) as error:
            self.log_error("Nie udało się udostępnić pliku %s: %s", filename, error)
            self.send_error(503, "Media temporarily unavailable")
            return None

        size = os.fstat(stream.fileno()).st_size
        start, end = 0, size - 1
        requested = self.headers.get("Range")
        if requested:
            match = HTTP_RANGE.fullmatch(requested)
            if match:
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), end) if last else end
                elif last:
                    start = max(0, size - int(last))
                else:
                    match = None
            if not match or not 0 <= start <= end < size:
                stream.close()
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None

        self.send_response(206 if requested else 200)
        self.send_header("Content-Type", mimetypes.guess_type(filename)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("Content-Length", str(end - start + 1))
        if requested:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        stream.seek(start)
        self.media_remaining = end - start + 1
        return stream

    def copyfile(self, source, output):
        if self.media_remaining is None:
            return super().copyfile(source, output)
        while self.media_remaining:
            chunk = source.read(min(128 * 1024, self.media_remaining))
            if not chunk:
                return
            try:
                output.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            self.media_remaining -= len(chunk)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    public = Path(__file__).resolve().parent.parent / "public"
    cache = MediaCache(public)
    with ThreadingHTTPServer(("127.0.0.1", args.port),
                             lambda *handler_args: Handler(*handler_args, cache=cache)) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
