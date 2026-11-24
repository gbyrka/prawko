"""Compact media encoding used by the static GitHub Pages export."""

from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


def pages_name(filename, crc, size, is_video, pjm):
    profile = "pjm" if pjm else "road" if is_video else "image"
    key = sha256(f"pages-v1\n{profile}\n{filename}\n{crc}\n{size}".encode()).hexdigest()
    return f"{key}.{'mp4' if is_video else 'webp'}"


def video_span(path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "packet=pts_time,dts_time,duration_time",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    starts, ends = [], []
    for line in probe.stdout.splitlines():
        fields = line.split(",")
        if len(fields) < 3:
            continue
        pts, dts, duration = fields[:3]
        timestamp = pts if pts != "N/A" else dts
        if timestamp != "N/A":
            start = float(timestamp)
            starts.append(start)
            ends.append(start + (0 if duration == "N/A" else float(duration)))
    if not starts:
        raise ValueError(f"{path.name}: film nie zawiera klatek.")
    return max(ends) - min(starts)


def encode_pages(source, destination, *, pjm, duration):
    if destination.is_file():
        return
    with TemporaryDirectory(dir=destination.parent) as temp:
        output = Path(temp) / destination.name
        if output.suffix == ".webp":
            command = [shutil.which("magick") or "convert", str(source), "-auto-orient",
                       "-resize", "1280x1280>", "-strip", "-quality", "83", str(output)]
        else:
            command = ["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-filter_threads", "1",
                       "-i", str(source), "-vf", "scale='min(iw,720)':-2",
                       "-map", "0:v:0", "-map", "0:a:0?", "-c:a", "aac", "-b:a", "64k",
                       "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p",
                       "-crf", "29", "-preset", "fast", "-threads", "1",
                       "-maxrate", "175k" if pjm else "250k", "-bufsize", "360k",
                       "-movflags", "+faststart", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode or not output.is_file() or output.stat().st_size == 0:
            raise ValueError(f"{source.name}: {result.stderr.strip() or 'Konwersja nie utworzyła pliku.'}")
        if output.suffix == ".mp4" and abs(duration(source) - duration(output)) > 0.30:
            # The WMV container can advertise trailing time beyond its last frame.
            if abs(video_span(source) - video_span(output)) > 0.30:
                raise ValueError(f"{source.name}: po konwersji zmienił się czas trwania filmu.")
        os.replace(output, destination)
