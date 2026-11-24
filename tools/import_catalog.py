#!/usr/bin/env python3
"""Prepare a version of the official question catalog for the static site."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from pages_media import encode_pages, pages_name
from remote_zip import ArchiveIndex, media_key
from topics import TOPICS, classify, normalize


ROOT = Path(__file__).resolve().parent.parent
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
CATEGORIES = ("AM", "A1", "A2", "A", "B1", "B", "C1", "C", "D1", "D", "T", "PT")
REQUIRED = ("Numer pytania", "Pytanie", "Odpowiedź A", "Odpowiedź B", "Odpowiedź C",
            "Poprawna odp", "Media", "Zakres struktury", "Liczba punktów", "Kategorie")
PJM_COLUMNS = ("Nazwa media tłumaczenie migowe (PJM) treść pyt",
               *("Nazwa media tłumaczenie migowe (PJM) treść odp " + c for c in "ABC"))
SOURCES = "https://www.gov.pl/web/infrastruktura/jak-uzyskac-prawo-jazdy#pytania-egzaminacyjne-na-prawo-jazdy"
CREDITS = "https://www.gov.pl/web/infrastruktura/ponowne-wykorzystanie-informacji-sektora-publicznego"
# These references are absent from the published ZIPs for 07.2026.
KNOWN_ABSENCES = {"11150": "dsc_0055.jpg", "13074": "5-9.2021.wmv"}
VIDEO = {".wmv", ".mp4", ".avi", ".mov", ".webm", ".mkv", ".mpg", ".mpeg"}
IMAGE = {".jpeg": "jpg", ".jpg": "jpg", ".png": "png", ".webp": "webp", ".gif": "gif"}


def xlsx_rows(path, sheet_name):
    with ZipFile(path) as book:
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        sheets = workbook.findall("x:sheets/x:sheet", NS)
        main = next((s for s in sheets if normalize(s.attrib["name"]) == normalize(sheet_name)
                     and s.get("state", "visible") == "visible"), None)
        if main is None:
            raise ValueError(f"Nie znaleziono widocznego arkusza {sheet_name!r}.")
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in relationships if r.attrib["Id"] == main.attrib[REL_ID])
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        sheet = ET.fromstring(book.read(sheet_path))
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            shared = ["".join(part.text or "" for part in item.findall(".//x:t", NS))
                      for item in ET.fromstring(book.read("xl/sharedStrings.xml"))]

        headers = {}
        for row in sheet.findall("x:sheetData/x:row", NS):
            values = {}
            for cell in row:
                column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                value = cell.findtext("x:v", default="", namespaces=NS)
                if cell.get("t") == "s":
                    value = shared[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(part.text or "" for part in cell.findall(".//x:t", NS))
                values[column] = value.strip()
            if not headers:
                headers = {column: value for column, value in values.items() if value}
                missing = set(REQUIRED) - set(headers.values())
                if missing:
                    raise ValueError("Brak wymaganych kolumn: " + ", ".join(sorted(missing)))
                continue
            yield {header: values.get(column, "") for column, header in headers.items()}


def read_questions(path, sheet, overrides):
    questions = []
    evidence_by_media = {}
    corrections = []
    seen = set()
    for row in xlsx_rows(path, sheet):
        number, prompt = row["Numer pytania"], row["Pytanie"]
        if not number and not prompt:
            continue
        if not re.fullmatch(r"[0-9]+", number) or not prompt or number in seen:
            raise ValueError(f"Nieprawidłowy lub powtórzony numer pytania: {number!r}")
        seen.add(number)

        category = set(filter(None, re.split(r"[,;\s]+", row["Kategorie"].upper())))
        if not category or category.difference(CATEGORIES):
            raise ValueError(f"Pytanie {number}: nieznane kategorie {category}.")
        choices = [row[f"Odpowiedź {letter}"] for letter in "ABC"]
        answer = row["Poprawna odp"].upper()
        if answer in {"T", "N", "TAK", "NIE"} and not any(choices):
            choices = [["T", "Tak"], ["N", "Nie"]]
            answer = answer[0]
            kind = "basic"
        elif answer in {"A", "B", "C"} and all(choices):
            choices = [[letter, text] for letter, text in zip("ABC", choices)]
            kind = "specialist"
        else:
            raise ValueError(f"Pytanie {number}: klucz odpowiedzi nie pasuje do dostępnych opcji.")
        declared = row["Zakres struktury"]
        expected = {"basic": "podstawowy", "specialist": "specjalistyczny"}[kind]
        if normalize(declared) != expected:
            corrections.append({"id": number, "source": declared, "used": expected})
        if row["Liczba punktów"] not in {"1", "2", "3"}:
            raise ValueError(f"Pytanie {number}: nieprawidłowa punktacja.")

        question = {
            "id": number, "text": prompt, "choices": choices, "answer": answer, "kind": kind,
            "points": int(row["Liczba punktów"]), "categories": [c for c in CATEGORIES if c in category],
        }
        main = row["Media"]
        question["topics"] = overrides.get(number) or classify(question, main)
        questions.append((question, main, [row.get(c, "") for c in PJM_COLUMNS]))
        if main and question["topics"] not in (["situations"], ["other"]):
            evidence_by_media.setdefault(filename_key(main), []).append(set(question["topics"]))
    if not questions:
        raise ValueError("Główny arkusz nie zawiera pytań.")
    for question, main, _ in questions:
        if question["id"] not in overrides and question["topics"] == ["situations"]:
            evidence = evidence_by_media.get(filename_key(main))
            if evidence:
                common = set.intersection(*evidence)
                if common:
                    question["topics"] = [topic for topic in TOPICS if topic in common]
    return questions, corrections


def index_media(archives):
    index = {}
    for archive in archives:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = normalize(PurePosixPath(info.filename).name.strip())
            if name in index:
                other_archive, other = index[name]
                if (info.CRC, info.file_size) != (other.CRC, other.file_size):
                    raise ValueError(f"Niejednoznaczny plik {info.filename!r} w {archive.filename} i {other_archive.filename}.")
            index[name] = (archive, info)
    return index


def remote_index(urls):
    index = {}
    for url in urls:
        with ArchiveIndex(url) as archive:
            for info, entry in archive.entries():
                name = normalize(PurePosixPath(info.filename).name.strip())
                previous = index.get(name)
                if previous and (previous["crc"], previous["size"]) != (entry["crc"], entry["size"]):
                    raise ValueError(f"Niejednoznaczny plik {info.filename!r} w katalogu zdalnym.")
                index[name] = entry
    return index


def deferred_media(references):
    resolved, index = {}, {}
    for key, entry in references.items():
        _, kind, ext = media_format(entry["filename"])
        filename = media_key(entry) + "." + ext
        resolved[key] = {"file": filename, "type": kind}
        index[filename] = entry
    return resolved, index


def filename_key(filename):
    return normalize(PurePosixPath(filename.replace("\\", "/")).name.strip())


def video_duration(path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=duration:format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    for line in probe.stdout.splitlines():
        if line and line != "N/A":
            return float(line)
    raise ValueError("Brak informacji o długości filmu.")


def media_format(filename):
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in VIDEO and suffix not in IMAGE:
        raise ValueError(f"Nieobsługiwany format: {filename}")
    return (suffix, "video", "mp4") if suffix in VIDEO else (suffix, "image", IMAGE[suffix])


def prepare_media(entry, directory):
    archive, info = entry
    return prepare_contents(archive.read(info), info.filename, directory)


def prepare_contents(contents, filename, directory):
    suffix, kind, ext = media_format(filename)
    is_video = kind == "video"
    digest = sha256(contents).hexdigest()
    asf_audio = bytes.fromhex("409e69f84d5bcf11a8fd00805f5c442b")
    may_have_audio = is_video and (suffix != ".wmv" or asf_audio in contents[:65536])
    encoding = "v2" if may_have_audio else "v1"
    destination = directory / f"{digest}-{encoding}.{ext}"
    repaired = directory / f"{digest}-{encoding}-repaired.{ext}"
    if repaired.exists():
        destination = repaired
    if not destination.exists():
        with TemporaryDirectory(dir=directory) as scratch:
            source = Path(scratch) / ("source" + suffix)
            source.write_bytes(contents)
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-threads", "1", "-i", str(source), "-map", "0:v:0"]
            if is_video:
                output = Path(scratch) / "output.mp4"
                command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "2",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
                if may_have_audio:
                    command += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "128k"]
                else:
                    command += ["-an"]
                command.append(str(output))
            else:
                output = source
                command += ["-an", "-f", "null", "-"]
            strict = [*command[:1], "-xerror", *command[1:]]
            check = subprocess.run(strict, capture_output=True, text=True, check=False)
            if is_video and check.returncode and "corrupt decoded frame" in check.stderr:
                # WMV sometimes flags a frame as corrupt despite a valid ZIP checksum.
                # Allow the decoder to recover, then ensure the clip remains whole.
                output.unlink(missing_ok=True)
                check = subprocess.run(command, capture_output=True, text=True, check=False)
                if not check.returncode:
                    original_time, output_time = video_duration(source), video_duration(output)
                    if output_time <= 0 or abs(original_time - output_time) > 0.25:
                        raise ValueError(f"{filename}: zmieniony czas trwania po odzyskiwaniu klatek.")
                    destination = repaired
            if check.returncode:
                raise ValueError(f"{filename}: {check.stderr.strip()}")
            os.replace(output, destination)
    return {"file": destination.name, "type": kind}


def prepare_pages_media(entry, directory, cached, group, previous_media):
    archive, info = entry
    suffix, kind, _ = media_format(info.filename)
    name = pages_name(info.filename, info.CRC, info.file_size, kind == "video", group == "pjm")
    target = cached / name
    previous = previous_media / name
    if previous.is_file():
        target = previous
    if not target.is_file():
        with TemporaryDirectory(dir=cached) as temp:
            source = Path(temp) / ("source" + suffix)
            source.write_bytes(archive.read(info))
            encode_pages(source, target, pjm=group == "pjm", duration=video_duration)
    shutil.copyfile(target, directory / name)
    return {"file": name, "type": kind}


def resolve_media(references, jobs, directory, pages_cache=None, previous_media=None):
    resolved, errors = {}, {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        tasks = {}
        for key, entry in references.items():
            if pages_cache is None:
                task = pool.submit(prepare_media, entry, directory)
            else:
                task = pool.submit(prepare_pages_media, entry, directory, pages_cache, key[0], previous_media)
            tasks[task] = key
        for completed, task in enumerate(as_completed(tasks), 1):
            key = tasks[task]
            try:
                resolved[key] = task.result()
            except (ValueError, OSError, BadZipFile, subprocess.CalledProcessError) as error:
                errors[key] = str(error)
            if completed % 200 == 0 or completed == len(tasks):
                print(f"Sprawdzono pliki: {completed}/{len(tasks)}", flush=True)
    return resolved, errors


def atomic_write(path, contents):
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(contents)
        temporary_path = Path(temp.name)
    try:
        temporary_path.chmod(0o644)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def validate_pools(questions):
    counts = Counter((category, question["kind"], question["points"])
                     for question in questions if not question.get("missingMedia")
                     for category in question["categories"])
    for category in CATEGORIES:
        for kind, quotas in (("basic", (4, 6, 10)), ("specialist", (2, 4, 6))):
            for points, required in enumerate(quotas, 1):
                if counts[category, kind, points] < required:
                    raise ValueError(f"Za mało pytań do egzaminu {category}: {kind}, {points} pkt.")


def compare_with_active(data, questions):
    pointer = data / "current.json"
    if not pointer.exists():
        return None
    name = json.loads(pointer.read_text())["catalog"]
    before = json.loads((data / name).read_text())
    previous = {q["id"]: q for q in before["questions"]}
    current = {q["id"]: q for q in questions}
    return {
        "previousVersion": before["version"],
        "added": sorted(current.keys() - previous.keys(), key=int),
        "removed": sorted(previous.keys() - current.keys(), key=int),
        "changed": sorted((number for number in current.keys() & previous.keys()
                           if current[number] != previous[number]), key=int),
    }


def run(args, *, pages_cache=None, previous_data=None, audit_path=None):
    if not all(shutil.which(command) for command in ("ffmpeg", "ffprobe")):
        raise ValueError("Import wymaga ffmpeg i ffprobe dostępnych w PATH.")
    overrides = json.loads((ROOT / "tools/topic_overrides.json").read_text())
    if any(not topics or len(set(topics)) != len(topics) or set(topics) - TOPICS.keys()
           for topics in overrides.values()):
        raise ValueError("Nieprawidłowy dział w topic_overrides.json.")
    prepared, corrections = read_questions(args.xlsx, args.sheet, overrides)
    output = args.output.resolve()
    directory = output / "media"
    data = output / "data"
    directory.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        if args.remote_media:
            main_index = remote_index(args.remote_media)
            pjm_index = remote_index([args.remote_pjm]) if args.remote_pjm else {}
        else:
            main_index = index_media([stack.enter_context(ZipFile(file)) for file in args.media])
            pjm_index = index_media([stack.enter_context(ZipFile(args.pjm))]) if args.pjm else {}
        references = {}
        for _, main, pjm in prepared:
            if filename_key(main) in main_index:
                references["media", filename_key(main)] = main_index[filename_key(main)]
            for name in (filename_key(file) for file in pjm):
                if name in pjm_index:
                    references["pjm", name] = pjm_index[name]
        remote_assets = {}
        if args.remote_media:
            resolved, remote_assets = deferred_media(references)
            conversion_errors = {}
        else:
            previous_media = previous_data.parent / "media" if previous_data else None
            resolved, conversion_errors = resolve_media(references, args.jobs, directory, pages_cache, previous_media)

    questions = []
    missing, unexpected = [], []
    pjm_count = 0
    for question, main, pjm in prepared:
        number = question["id"]
        if main:
            key = "media", filename_key(main)
            if key in resolved:
                question["media"] = resolved[key]
            else:
                question["missingMedia"] = True
                item = {"id": number, "file": main, "reason": conversion_errors.get(key, "Brak w ZIP")}
                missing.append(item)
                if key in conversion_errors or KNOWN_ABSENCES.get(number) != key[1]:
                    unexpected.append(item)
        if args.pjm or args.remote_pjm:
            for label, name in zip(("question", "A", "B", "C"), pjm):
                if name:
                    media = resolved.get(("pjm", filename_key(name)))
                    if media:
                        question.setdefault("pjm", {})[label] = media
                        pjm_count += 1
                    else:
                        key = "pjm", filename_key(name)
                        unexpected.append({"id": number, "file": name,
                                           "reason": conversion_errors.get(key, "Brak w ZIP tłumaczeń")})
        signature = [question[field] for field in ("text", "choices", "answer", "points")]
        signature.append(question.get("media"))
        question["revision"] = sha256(json_bytes(signature)).hexdigest()[:20]
        questions.append(question)

    catalog = {"version": args.version, "source": SOURCES, "credits": CREDITS,
               "topics": TOPICS, "questions": questions}
    content = json_bytes(catalog)
    index_content = json_bytes(remote_assets)
    digest = sha256(content + index_content).hexdigest()[:16]
    catalog_file = f"catalog-{digest}.json"
    report = {"version": args.version, "questions": len(questions), "catalog": catalog_file,
              "mediaFiles": len(resolved), "mediaVerifiedOnDemand": bool(remote_assets),
              "pjmReferences": pjm_count, "missingMedia": missing,
              "unexpectedMediaProblems": unexpected, "questionTypesCorrected": corrections,
              "changes": compare_with_active(previous_data or data, questions),
              "recoveredVideos": [name for (_, name), entry in resolved.items() if "-repaired." in entry["file"]],
              "topics": dict(Counter(topic for q in questions for topic in q["topics"])),
              "questionsWithoutSpecificTopic": [q["id"] for q in questions if q["topics"] in (["situations"], ["other"])]}
    report_path = data / f"report-{digest}.json"
    atomic_write(report_path, json_bytes(report))
    if audit_path:
        atomic_write(audit_path, json_bytes(report))
    if unexpected:
        raise ValueError(f"{len(unexpected)} problemów z multimediami. Szczegóły: {audit_path or report_path}")
    validate_pools(questions)
    if remote_assets:
        atomic_write(data / f"media-index-{digest}.json", index_content)
    atomic_write(data / catalog_file, content)
    if args.activate:
        atomic_write(data / "current.json", json_bytes({"catalog": catalog_file}))
    print(f"Pytania: {len(questions)} | pliki: {len(resolved)} | znane braki: {len(missing)}")
    print(f"Katalog: {data / catalog_file} | raport: {data / ('report-' + digest + '.json')}")
    print("Wersja aktywna." if args.activate else "Wersja gotowa do sprawdzenia.")
    return report


def export_pages(args):
    if not (shutil.which("magick") or shutil.which("convert")):
        raise ValueError("Eksport Pages wymaga ImageMagick dostępnego w PATH.")
    output = (args.output or ROOT / "docs").resolve()
    if output.exists() and (not output.is_dir() or (any(output.iterdir()) and not
                            (output / ".nojekyll").is_file())):
        raise ValueError(f"Katalog {output} nie jest wygenerowanym eksportem Pages.")
    cache = ROOT / "sources/pages-cache"
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".prawko-pages-", dir=output.parent) as temporary:
        temp = Path(temporary)
        stage = temp / "site"
        args.output, args.activate = stage, True
        report = run(args, pages_cache=cache, previous_data=output / "data",
                     audit_path=cache.parent / "pages-report.json")
        for filename in ("index.html", "app.mjs", "exam.mjs", "styles.css"):
            shutil.copyfile(ROOT / "public" / filename, stage / filename)
        (stage / ".nojekyll").touch()
        size = sum(f.stat().st_size for f in stage.rglob("*") if f.is_file())
        if size > 950_000_000:
            raise ValueError(f"Eksport ma {size / 1_000_000:.1f} MB. Przekracza budżet 950 MB.")
        previous = temp / "previous"
        if output.exists():
            output.rename(previous)
        try:
            stage.rename(output)
        except OSError:
            if previous.exists():
                previous.rename(output)
            raise
    print(f"GitHub Pages: {output} | {size / 1_000_000:.1f} MB | {report['mediaFiles']} multimediów", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--media", type=Path, nargs="+", help="Archiwa zdjęć i filmów na dysku")
    source.add_argument("--remote-media", nargs="+", metavar="HTTPS", help="Adresy ZIP ze zdjęciami i filmami")
    parser.add_argument("--pjm", type=Path, help="Archiwum tłumaczeń migowych na dysku")
    parser.add_argument("--remote-pjm", metavar="HTTPS", help="Adres ZIP z tłumaczeniami migowymi")
    parser.add_argument("--version", required=True, help="Oznaczenie wydania, np. 07.2026")
    parser.add_argument("--sheet", default="katalog")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pages", action="store_true", help="Przygotuj kompletny eksport do docs/")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs musi być większe od zera.")
    if (args.pjm and args.remote_media) or (args.remote_pjm and args.media):
        parser.error("Archiwa PJM i multimediów muszą pochodzić z tego samego trybu importu.")
    if args.pages and args.remote_media:
        parser.error("--pages wymaga lokalnych archiwów ZIP.")
    try:
        if args.pages:
            export_pages(args)
        else:
            args.output = args.output or ROOT / "public"
            run(args)
    except (ValueError, OSError, BadZipFile) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
