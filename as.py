#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import shutil
import asyncio
import tempfile
import subprocess
import urllib.request
import tarfile
from pathlib import Path


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = "8516594546:AAEteo2jtuEEDr0jiQdIHV3h6IKNUSenfoI"

WEBTOR_URL = "https://webtor.io/{}"

MAX_TORRENT_SIZE = 20 * 1024 * 1024

# البيانات التي نسمح بتنزيلها للعينة.
# لا يتم إرسالها كلها.
SAMPLE_SIZES = [
    64 * 1024 * 1024,
    128 * 1024 * 1024,
    256 * 1024 * 1024
]

SAMPLE_SECONDS = 10

METADATA_TIMEOUT = 120
SAMPLE_TIMEOUT = 240

BASE_DIR = Path.home()

LOCAL_BIN = (
    BASE_DIR
    / ".local"
    / "bin"
)

FFMPEG_DIR = (
    BASE_DIR
    / ".local"
    / "ffmpeg"
)

LOCAL_BIN.mkdir(
    parents=True,
    exist_ok=True
)

FFMPEG_DIR.mkdir(
    parents=True,
    exist_ok=True
)

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
    ".m4v",
    ".ts",
    ".m2ts",
    ".mts",
    ".flv",
    ".wmv",
    ".mpg",
    ".mpeg",
    ".3gp"
}

SUBTITLE_EXTENSIONS = {
    ".srt",
    ".ass",
    ".ssa",
    ".vtt",
    ".sub",
    ".idx",
    ".sup"
}

AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".aac",
    ".m4a",
    ".ogg",
    ".opus",
    ".ac3",
    ".eac3",
    ".dts"
}

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp"
}


# =========================================================
# INSTALL PYTHON PACKAGES
# =========================================================

def install_package(
    package,
    import_name=None
):

    import_name = (
        import_name
        or package
    )

    try:

        __import__(
            import_name
        )

        return

    except ImportError:
        pass

    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--user",
        package
    ])


install_package(
    "requests"
)

install_package(
    "beautifulsoup4",
    "bs4"
)

install_package(
    "python-telegram-bot"
)

install_package(
    "libtorrent"
)


import requests

from bs4 import BeautifulSoup

import libtorrent as lt

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.constants import (
    ChatAction
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)


# =========================================================
# HELPERS
# =========================================================

def clean_text(value):

    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def human_size(size):

    try:
        size = float(size)

    except Exception:
        return "غير معروف"

    units = [
        "B",
        "KB",
        "MB",
        "GB",
        "TB"
    ]

    for unit in units:

        if size < 1024:

            if unit == "B":
                return f"{int(size)} {unit}"

            return f"{size:.2f} {unit}"

        size /= 1024

    return f"{size:.2f} PB"


def get_ext(filename):

    return Path(
        str(filename)
    ).suffix.lower()


def is_video(filename):

    return (
        get_ext(filename)
        in VIDEO_EXTENSIONS
    )


def is_subtitle(filename):

    return (
        get_ext(filename)
        in SUBTITLE_EXTENSIONS
    )


def is_audio(filename):

    return (
        get_ext(filename)
        in AUDIO_EXTENSIONS
    )


def is_image(filename):

    return (
        get_ext(filename)
        in IMAGE_EXTENSIONS
    )


def extract_infohash(text):

    if not text:
        return None

    match = re.search(
        r"urn:btih:([a-fA-F0-9]{40})",
        text,
        re.I
    )

    if match:
        return (
            match.group(1)
            .lower()
        )

    match = re.search(
        r"\b([a-fA-F0-9]{40})\b",
        text
    )

    if match:
        return (
            match.group(1)
            .lower()
        )

    return None


# =========================================================
# WEBTOR METADATA
# =========================================================

def get_webtor_info(
    infohash
):

    url = WEBTOR_URL.format(
        infohash
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0 "
            "(Linux; Android 13) "
            "AppleWebKit/537.36 "
            "Chrome/140 Safari/537.36"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    result = {
        "title": "",
        "year": "",
        "rating": "",
        "votes": "",
        "description": "",
        "poster": ""
    }

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    title = ""

    tag = soup.find(
        "meta",
        attrs={
            "property": "og:title"
        }
    )

    if tag:

        title = tag.get(
            "content",
            ""
        )

    if not title:

        h1 = soup.find(
            "h1"
        )

        if h1:

            title = h1.get_text(
                " ",
                strip=True
            )

    if not title and soup.title:

        title = soup.title.get_text(
            " ",
            strip=True
        )

    title = re.sub(
        r"\s*\|\s*Webtor\.io\s*$",
        "",
        title,
        flags=re.I
    )

    result["title"] = clean_text(
        title
    )

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

    tag = soup.find(
        "meta",
        attrs={
            "name": "description"
        }
    )

    if tag:

        result["description"] = clean_text(
            tag.get(
                "content",
                ""
            )
        )

    if not result["description"]:

        tag = soup.find(
            "meta",
            attrs={
                "property":
                    "og:description"
            }
        )

        if tag:

            result["description"] = clean_text(
                tag.get(
                    "content",
                    ""
                )
            )

    # -----------------------------------------------------
    # POSTER
    # -----------------------------------------------------

    tag = soup.find(
        "meta",
        attrs={
            "property":
                "og:image"
        }
    )

    if tag:

        result["poster"] = tag.get(
            "content",
            ""
        )

    # -----------------------------------------------------
    # PAGE TEXT
    # -----------------------------------------------------

    page_text = soup.get_text(
        "\n",
        strip=True
    )

    # -----------------------------------------------------
    # YEAR
    # -----------------------------------------------------

    match = re.search(
        r"\b(19\d{2}|20\d{2})\b",
        page_text
    )

    if match:

        result["year"] = (
            match.group(1)
        )

    # -----------------------------------------------------
    # RATING
    # -----------------------------------------------------

    patterns = [

        r"rating[^0-9]{0,30}"
        r"([0-9]+(?:\.[0-9]+)?)",

        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*/\s*10"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page_text,
            re.I
        )

        if match:

            result["rating"] = (
                match.group(1)
            )

            break

    # -----------------------------------------------------
    # VOTES
    # -----------------------------------------------------

    patterns = [

        r"([0-9][0-9,.\s]*)"
        r"\s*(?:ratings|votes)",

        r"(?:ratings|votes)"
        r"[^0-9]{0,20}"
        r"([0-9][0-9,.\s]*)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page_text,
            re.I
        )

        if match:

            result["votes"] = clean_text(
                match.group(1)
            )

            break

    return result


# =========================================================
# FFMPEG
# =========================================================

def find_ffmpeg():

    candidates = [

        shutil.which(
            "ffmpeg"
        ),

        LOCAL_BIN / "ffmpeg",

        FFMPEG_DIR / "ffmpeg",

        BASE_DIR
        / "bin"
        / "ffmpeg",

        BASE_DIR
        / "ffmpeg"
        / "ffmpeg"
    ]

    for candidate in candidates:

        if not candidate:
            continue

        path = Path(
            candidate
        ).expanduser()

        if (
            path.exists()
            and path.is_file()
            and os.access(
                path,
                os.X_OK
            )
        ):

            return str(path)

    return None


def install_ffmpeg():

    existing = find_ffmpeg()

    if existing:

        print(
            "[+] FFmpeg:",
            existing
        )

        return existing

    print(
        "[+] FFmpeg غير موجود."
    )

    print(
        "[+] جاري تنزيل نسخة Linux x86_64..."
    )

    # رابط ثابت لآخر static Linux x86_64 GPL
    url = (
        "https://github.com/"
        "BtbN/FFmpeg-Builds/"
        "releases/latest/download/"
        "ffmpeg-master-latest-linux64-gpl.tar.xz"
    )

    archive = (
        FFMPEG_DIR
        / "ffmpeg.tar.xz"
    )

    extract_dir = (
        FFMPEG_DIR
        / "extract"
    )

    # -----------------------------------------------------
    # DOWNLOAD
    # -----------------------------------------------------

    if not archive.exists():

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "OrbitBot/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=60
        ) as response:

            total = response.headers.get(
                "Content-Length"
            )

            total = (
                int(total)
                if total
                else 0
            )

            downloaded = 0

            with open(
                archive,
                "wb"
            ) as output:

                while True:

                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    output.write(
                        chunk
                    )

                    downloaded += len(
                        chunk
                    )

                    if total:

                        percent = (
                            downloaded
                            * 100
                            / total
                        )

                        print(
                            f"\r[FFMPEG] "
                            f"{percent:.1f}%",
                            end="",
                            flush=True
                        )

        print()

    # -----------------------------------------------------
    # EXTRACT
    # -----------------------------------------------------

    if not extract_dir.exists():

        extract_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        print(
            "[+] فك ضغط FFmpeg..."
        )

        with tarfile.open(
            archive,
            mode="r:xz"
        ) as tar:

            tar.extractall(
                extract_dir
            )

    # -----------------------------------------------------
    # FIND BINARY
    # -----------------------------------------------------

    ffmpeg_source = None
    ffprobe_source = None

    for path in extract_dir.rglob(
        "ffmpeg"
    ):

        if (
            path.is_file()
            and os.access(
                path,
                os.X_OK
            )
        ):

            ffmpeg_source = path
            break

    for path in extract_dir.rglob(
        "ffprobe"
    ):

        if (
            path.is_file()
            and os.access(
                path,
                os.X_OK
            )
        ):

            ffprobe_source = path
            break

    if not ffmpeg_source:

        raise RuntimeError(
            "تم تنزيل FFmpeg لكن لم "
            "أجد الملف التنفيذي."
        )

    target = (
        LOCAL_BIN
        / "ffmpeg"
    )

    shutil.copy2(
        ffmpeg_source,
        target
    )

    target.chmod(
        0o755
    )

    if ffprobe_source:

        probe_target = (
            LOCAL_BIN
            / "ffprobe"
        )

        shutil.copy2(
            ffprobe_source,
            probe_target
        )

        probe_target.chmod(
            0o755
        )

    print(
        "[+] FFmpeg installed:",
        target
    )

    return str(target)


# =========================================================
# LIBTORRENT SESSION
# =========================================================

def create_session():

    session = lt.session()

    try:

        session.listen_on(
            6881,
            6891
        )

    except Exception as e:

        print(
            "[LISTEN]",
            repr(e)
        )

    routers = [
        (
            "router.bittorrent.com",
            6881
        ),
        (
            "dht.transmissionbt.com",
            6881
        ),
        (
            "router.utorrent.com",
            6881
        )
    ]

    for router in routers:

        try:

            session.add_dht_node(
                router
            )

        except Exception:
            pass

    return session


# =========================================================
# METADATA WAIT
# =========================================================

def wait_metadata(
    handle,
    timeout=METADATA_TIMEOUT
):

    start = time.time()

    while (
        time.time() - start
        < timeout
    ):

        try:

            status = (
                handle.status()
            )

            if status.has_metadata:

                return True

        except Exception:
            pass

        time.sleep(
            0.5
        )

    return False


# =========================================================
# FILE STORAGE
# =========================================================

def get_file_storage(ti):

    # libtorrent 2.1
    # file_storage() هو البديل الحديث
    # عن files()

    try:

        return ti.file_storage()

    except AttributeError:

        # fallback للإصدارات الأقدم
        return ti.files()


def torrent_files(ti):

    fs = get_file_storage(
        ti
    )

    result = []

    for i in range(
        fs.num_files()
    ):

        name = fs.file_path(
            i
        )

        size = fs.file_size(
            i
        )

        result.append({

            "index": i,

            "name": name,

            "size": size
        })

    return result


# =========================================================
# STATISTICS
# =========================================================

def get_statistics(ti):

    files = torrent_files(
        ti
    )

    video = []
    subtitles = []
    audio = []
    images = []
    other = []

    for item in files:

        name = item["name"]

        if is_video(name):

            video.append(
                item
            )

        elif is_subtitle(name):

            subtitles.append(
                item
            )

        elif is_audio(name):

            audio.append(
                item
            )

        elif is_image(name):

            images.append(
                item
            )

        else:

            other.append(
                item
            )

    return {

        "files": files,

        "video": video,

        "subtitles": subtitles,

        "audio": audio,

        "images": images,

        "other": other,

        "file_count":
            len(files),

        "video_count":
            len(video),

        "subtitle_count":
            len(subtitles),

        "audio_count":
            len(audio),

        "image_count":
            len(images),

        "other_count":
            len(other),

        "total_size":
            ti.total_size()
    }


# =========================================================
# MAIN VIDEO
# =========================================================

def find_main_video(ti):

    videos = []

    for item in torrent_files(
        ti
    ):

        if is_video(
            item["name"]
        ):

            videos.append(
                item
            )

    if not videos:

        return None

    videos.sort(
        key=lambda x: x["size"],
        reverse=True
    )

    return videos[0]


# =========================================================
# LOCATE DOWNLOADED FILE
# =========================================================

def locate_file(
    save_path,
    ti,
    file_index
):

    fs = get_file_storage(
        ti
    )

    relative = Path(
        fs.file_path(
            file_index
        )
    )

    candidates = [

        Path(save_path)
        / relative,

        Path(save_path)
        / ti.name()
        / relative
    ]

    for candidate in candidates:

        if candidate.exists():

            return candidate

    # fallback
    filename = relative.name

    matches = list(
        Path(save_path).rglob(
            filename
        )
    )

    if matches:

        # الأكبر غالبًا الملف الحقيقي
        matches.sort(
            key=lambda p: p.stat().st_size,
            reverse=True
        )

        return matches[0]

    return candidates[0]


# =========================================================
# REQUEST PIECES
# =========================================================

def request_sample_pieces(
    handle,
    ti,
    file_index,
    wanted_bytes
):

    fs = get_file_storage(
        ti
    )

    piece_length = (
        ti.piece_length()
    )

    piece_count = (
        ti.num_pieces()
    )

    file_size = (
        fs.file_size(
            file_index
        )
    )

    wanted_bytes = min(
        wanted_bytes,
        file_size
    )

    file_offset = (
        fs.file_offset(
            file_index
        )
    )

    first_piece = (
        file_offset
        // piece_length
    )

    last_byte = (
        file_offset
        + wanted_bytes
        - 1
    )

    last_piece = (
        last_byte
        // piece_length
    )

    first_piece = max(
        0,
        first_piece
    )

    last_piece = min(
        piece_count - 1,
        last_piece
    )

    priorities = [
        0
    ] * piece_count

    for piece in range(
        first_piece,
        last_piece + 1
    ):

        priorities[piece] = 7

    handle.prioritize_pieces(
        priorities
    )

    required = (
        last_piece
        - first_piece
        + 1
    )

    print(
        "[+] Piece length:",
        human_size(
            piece_length
        )
    )

    print(
        "[+] Pieces:",
        piece_count
    )

    print(
        "[+] Downloading pieces:",
        first_piece,
        "to",
        last_piece
    )

    print(
        "[+] Piece count:",
        required
    )

    return (
        first_piece,
        last_piece,
        required
    )


# =========================================================
# WAIT PIECES
# =========================================================

def wait_pieces(
    handle,
    first_piece,
    last_piece,
    timeout=SAMPLE_TIMEOUT
):

    start = time.time()

    required = (
        last_piece
        - first_piece
        + 1
    )

    while True:

        if (
            time.time() - start
            > timeout
        ):

            raise TimeoutError(
                "انتهت مهلة جلب قطع العينة."
            )

        status = (
            handle.status()
        )

        pieces = (
            status.pieces
        )

        completed = 0

        for piece in range(
            first_piece,
            last_piece + 1
        ):

            try:

                if pieces[piece]:

                    completed += 1

            except Exception:
                pass

        print(
            f"\r[DOWNLOAD] "
            f"{completed}/{required}",
            end="",
            flush=True
        )

        if completed >= required:

            print()

            return

        time.sleep(
            0.5
        )


# =========================================================
# CREATE PREVIEW
# =========================================================

def make_preview(
    ffmpeg,
    source,
    output
):

    print(
        "[+] Creating 10 second preview..."
    )

    command = [

        ffmpeg,

        "-hide_banner",

        "-loglevel",
        "error",

        "-y",

        "-ss",
        "0",

        "-i",
        str(source),

        "-t",
        str(SAMPLE_SECONDS),

        "-map",
        "0:v:0",

        "-map",
        "0:a:0?",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "28",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-movflags",
        "+faststart",

        str(output)
    ]

    result = subprocess.run(

        command,

        stdout=subprocess.PIPE,

        stderr=subprocess.PIPE,

        text=True,

        timeout=120
    )

    if result.returncode != 0:

        error = (
            result.stderr.strip()
            or "FFmpeg failed"
        )

        raise RuntimeError(
            error
        )

    if not output.exists():

        raise RuntimeError(
            "FFmpeg لم ينشئ العينة."
        )

    if (
        output.stat().st_size
        <= 0
    ):

        raise RuntimeError(
            "ملف العينة فارغ."
        )


# =========================================================
# DOWNLOAD SAMPLE
# =========================================================

def download_sample(
    source,
    source_type
):

    workdir = tempfile.mkdtemp(
        prefix="orbit_sample_",
        dir=str(
            BASE_DIR
            / "admin"
            / "tmp"
        )
        if (
            BASE_DIR
            / "admin"
            / "tmp"
        ).exists()
        else None
    )

    session = None
    handle = None

    try:

        # -------------------------------------------------
        # FFmpeg
        # -------------------------------------------------

        ffmpeg = install_ffmpeg()

        # -------------------------------------------------
        # SESSION
        # -------------------------------------------------

        session = create_session()

        save_path = Path(
            workdir
        )

        # -------------------------------------------------
        # ADD TORRENT
        # -------------------------------------------------

        if source_type == "magnet":

            params = (
                lt.parse_magnet_uri(
                    source
                )
            )

            params.save_path = (
                str(save_path)
            )

            handle = (
                session.add_torrent(
                    params
                )
            )

            print(
                "[+] Waiting metadata..."
            )

            if not wait_metadata(
                handle
            ):

                raise RuntimeError(
                    "لم يتم الحصول على Metadata من Magnet."
                )

        else:

            ti_input = lt.torrent_info(
                source
            )

            params = (
                lt.add_torrent_params()
            )

            params.ti = ti_input

            params.save_path = (
                str(save_path)
            )

            handle = (
                session.add_torrent(
                    params
                )
            )

        # -------------------------------------------------
        # TORRENT INFO
        # -------------------------------------------------

        ti = handle.torrent_file()

        if ti is None:

            raise RuntimeError(
                "torrent_info غير متوفر."
            )

        torrent_name = ti.name()

        torrent_size = (
            ti.total_size()
        )

        print(
            "[TORRENT]",
            torrent_name
        )

        print(
            "[TOTAL SIZE]",
            human_size(
                torrent_size
            )
        )

        # -------------------------------------------------
        # MAIN VIDEO
        # -------------------------------------------------

        video = find_main_video(
            ti
        )

        if video is None:

            raise RuntimeError(
                "لم يتم العثور على فيديو."
            )

        file_index = (
            video["index"]
        )

        video_name = (
            video["name"]
        )

        video_size = (
            video["size"]
        )

        print(
            "[VIDEO]",
            video_name
        )

        print(
            "[VIDEO SIZE]",
            human_size(
                video_size
            )
        )

        # -------------------------------------------------
        # TRY 64MB -> 128MB -> 256MB
        # -------------------------------------------------

        source_file = None
        preview = None

        for wanted_bytes in SAMPLE_SIZES:

            wanted_bytes = min(
                wanted_bytes,
                video_size
            )

            print(
                "\n================================"
            )

            print(
                "[+] Sample target:",
                human_size(
                    wanted_bytes
                )
            )

            print(
                "================================"
            )

            first_piece, last_piece, required = (
                request_sample_pieces(
                    handle,
                    ti,
                    file_index,
                    wanted_bytes
                )
            )

            wait_pieces(
                handle,
                first_piece,
                last_piece
            )

            source_file = locate_file(
                save_path,
                ti,
                file_index
            )

            print(
                "[+] Source:",
                source_file
            )

            if not source_file.exists():

                raise RuntimeError(
                    "لم يتم العثور على ملف الفيديو."
                )

            # الحجم الفعلي الذي صار موجودًا
            try:

                physical_size = (
                    source_file.stat().st_size
                )

                print(
                    "[+] Local file size:",
                    human_size(
                        physical_size
                    )
                )

            except Exception:
                pass

            preview = (
                save_path
                / "preview.mp4"
            )

            try:

                make_preview(
                    ffmpeg,
                    source_file,
                    preview
                )

                print(
                    "[+] Preview created:"
                )

                print(
                    human_size(
                        preview.stat().st_size
                    )
                )

                break

            except Exception as e:

                print(
                    "[+] FFmpeg sample attempt failed:"
                )

                print(
                    repr(e)
                )

                try:

                    preview.unlink(
                        missing_ok=True
                    )

                except Exception:
                    pass

                preview = None

                if (
                    wanted_bytes
                    >= min(
                        SAMPLE_SIZES[-1],
                        video_size
                    )
                ):

                    raise

                print(
                    "[+] Trying larger sample..."
                )

        if not preview:

            raise RuntimeError(
                "تعذر إنشاء عينة الفيديو."
            )

        statistics = get_statistics(
            ti
        )

        return {

            "preview":
                str(preview),

            "torrent_name":
                torrent_name,

            "torrent_size":
                torrent_size,

            "video_name":
                video_name,

            "video_size":
                video_size,

            "statistics":
                statistics,

            "workdir":
                workdir
        }

    finally:

        try:

            if handle is not None:

                handle.pause()

        except Exception:
            pass

        try:

            if (
                session is not None
                and handle is not None
            ):

                session.remove_torrent(
                    handle
                )

        except Exception:
            pass


# =========================================================
# CAPTION
# =========================================================

def make_caption(
    info,
    sample
):

    statistics = (
        sample["statistics"]
    )

    title = (
        info.get("title")
        or sample[
            "torrent_name"
        ]
    )

    year = (
        info.get("year")
        or "غير معروف"
    )

    rating = (
        info.get("rating")
        or "غير معروف"
    )

    votes = (
        info.get("votes")
        or "غير معروف"
    )

    description = (
        info.get("description")
        or "لا يوجد وصف."
    )

    # -----------------------------------------------------
    # InfoHash
    # -----------------------------------------------------

    infohash = (
        sample.get(
            "infohash"
        )
        or ""
    )

    lines = [

        "معلومات العمل",

        "",

        f"العنوان: {title}",

        f"العنوان الأصلي: {title}",

        f"السنة: {year}",

        "النوع: فيلم",

        f"التقييم: {rating}/10",

        f"عدد التقييمات: {votes}",

        "التصنيف: غير معروف",

        "",

        "الوصف:",

        description,

        "",

        "معلومات التورنت",

        "",

        (
            "اسم التورنت: "
            + sample[
                "torrent_name"
            ]
        ),

        (
            "الحجم: "
            + human_size(
                sample[
                    "torrent_size"
                ]
            )
        ),

        (
            "عدد الملفات: "
            + str(
                statistics[
                    "file_count"
                ]
            )
        ),

        (
            "الفيديو: "
            + str(
                statistics[
                    "video_count"
                ]
            )
        ),

        (
            "الترجمة: "
            + str(
                statistics[
                    "subtitle_count"
                ]
            )
        ),

        (
            "الصوت: "
            + str(
                statistics[
                    "audio_count"
                ]
            )
        ),

        (
            "الصور: "
            + str(
                statistics[
                    "image_count"
                ]
            )
        ),

        (
            "أخرى: "
            + str(
                statistics[
                    "other_count"
                ]
            )
        ),

        "",

        "InfoHash:",

        infohash,

        "",

        "الفيديوهات:"
    ]

    for item in (
        statistics["video"]
    ):

        lines.append(
            "• "
            + item["name"]
        )

        lines.append(
            "  "
            + human_size(
                item["size"]
            )
        )

    return "\n".join(
        lines
    )


# =========================================================
# SEND RESULT
# =========================================================

async def send_result(
    message,
    info,
    sample
):

    caption = make_caption(
        info,
        sample
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Webtor",
                    url=WEBTOR_URL.format(
                        sample[
                            "infohash"
                        ]
                    )
                )
            ]
        ]
    )

    poster = (
        info.get("poster")
    )

    if poster:

        try:

            await message.reply_photo(
                photo=poster,
                caption=caption,
                reply_markup=keyboard
            )

        except Exception:

            await message.reply_text(
                caption,
                reply_markup=keyboard
            )

    else:

        await message.reply_text(
            caption,
            reply_markup=keyboard
        )

    preview = (
        sample["preview"]
    )

    if os.path.exists(
        preview
    ):

        try:

            await message.chat.send_action(
                ChatAction.UPLOAD_VIDEO
            )

        except Exception:
            pass

        with open(
            preview,
            "rb"
        ) as video:

            await message.reply_video(
                video=video,
                caption=(
                    "عينة من بداية الفيديو\n"
                    "المدة: 10 ثواني"
                ),
                supports_streaming=True
            )


# =========================================================
# MAGNET
# =========================================================

async def process_magnet(
    update,
    magnet
):

    message = (
        update.message
    )

    infohash = extract_infohash(
        magnet
    )

    if not infohash:

        await message.reply_text(
            "لم أستطع استخراج InfoHash."
        )

        return

    status = await message.reply_text(
        "جاري جلب معلومات التورنت..."
    )

    sample = None

    try:

        # -------------------------------------------------
        # Webtor = metadata only
        # -------------------------------------------------

        info = await asyncio.to_thread(
            get_webtor_info,
            infohash
        )

        await status.edit_text(
            "تم جلب معلومات العمل.\n"
            "جاري جلب بداية الفيديو..."
        )

        # -------------------------------------------------
        # Torrent = sample
        # -------------------------------------------------

        sample = await asyncio.to_thread(
            download_sample,
            magnet,
            "magnet"
        )

        sample["infohash"] = (
            infohash
        )

        await send_result(
            message,
            info,
            sample
        )

        try:

            await status.delete()

        except Exception:
            pass

    except Exception as e:

        print(
            "\n[SAMPLE ERROR]",
            repr(e)
        )

        try:

            await status.edit_text(
                "حدث خطأ أثناء جلب عينة الفيديو:\n"
                + str(e)
            )

        except Exception:
            pass

    finally:

        if sample:

            shutil.rmtree(
                sample["workdir"],
                ignore_errors=True
            )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "أرسل ملف .torrent أو Magnet Link."
    )


# =========================================================
# TEXT
# =========================================================

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        update.message.text
        or ""
    ).strip()

    if text.startswith(
        "magnet:"
    ):

        await process_magnet(
            update,
            text
        )

        return

    infohash = extract_infohash(
        text
    )

    if infohash:

        magnet = (
            "magnet:?xt=urn:btih:"
            + infohash
        )

        await process_magnet(
            update,
            magnet
        )

        return

    await update.message.reply_text(
        "أرسل Magnet Link أو ملف .torrent."
    )


# =========================================================
# TORRENT FILE
# =========================================================

async def handle_torrent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    document = (
        update.message.document
    )

    if not document:
        return

    filename = (
        document.file_name
        or ""
    )

    if not filename.lower().endswith(
        ".torrent"
    ):

        await update.message.reply_text(
            "الملف يجب أن يكون .torrent"
        )

        return

    if (
        document.file_size
        and document.file_size
        > MAX_TORRENT_SIZE
    ):

        await update.message.reply_text(
            "ملف التورنت أكبر من الحد المسموح."
        )

        return

    status = await update.message.reply_text(
        "جاري استلام التورنت..."
    )

    temp_dir = tempfile.mkdtemp(
        prefix="orbit_input_"
    )

    torrent_path = (
        Path(temp_dir)
        / filename
    )

    sample = None

    try:

        telegram_file = (
            await context.bot.get_file(
                document.file_id
            )
        )

        await telegram_file.download_to_drive(
            custom_path=str(
                torrent_path
            )
        )

        # -------------------------------------------------
        # Read torrent metadata
        # -------------------------------------------------

        ti = lt.torrent_info(
            str(torrent_path)
        )

        infohash = str(
            ti.info_hash()
        )

        print(
            "[INFOHASH]",
            infohash
        )

        # -------------------------------------------------
        # Webtor metadata
        # -------------------------------------------------

        info = await asyncio.to_thread(
            get_webtor_info,
            infohash
        )

        await status.edit_text(
            "تم استلام التورنت.\n"
            "جاري جلب بداية الفيديو..."
        )

        # -------------------------------------------------
        # Sample
        # -------------------------------------------------

        sample = await asyncio.to_thread(
            download_sample,
            str(torrent_path),
            "torrent"
        )

        sample["infohash"] = (
            infohash
        )

        await send_result(
            update.message,
            info,
            sample
        )

        try:

            await status.delete()

        except Exception:
            pass

    except Exception as e:

        print(
            "\n[SAMPLE ERROR]",
            repr(e)
        )

        try:

            await status.edit_text(
                "حدث خطأ أثناء جلب عينة الفيديو:\n"
                + str(e)
            )

        except Exception:
            pass

    finally:

        if sample:

            shutil.rmtree(
                sample["workdir"],
                ignore_errors=True
            )

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================================================
# MAIN
# =========================================================

def main():

    if (
        not BOT_TOKEN
        or BOT_TOKEN
        == "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE"
    ):

        print(
            "ضع BOT_TOKEN أولاً."
        )

        return

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_torrent
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text
        )
    )

    print(
        "Bot started..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":

    main()