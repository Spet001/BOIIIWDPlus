"""
Flask API for BOIII Workshop Downloader (Electron build)

Reimplements the Tkinter behaviours in a backend-friendly manner so the
Electron UI can rely on the very same SteamCMD driven workflows.
"""

from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BOIIIWD_DATA_DIR", PROJECT_ROOT))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE_PATH = DATA_DIR / "config.ini"
STEAM_APP_ID = "311210"
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={id}"
ITEM_INFO_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"


def ensure_config_file() -> None:
    config = configparser.ConfigParser()
    if CONFIG_FILE_PATH.exists():
        return

    config["Settings"] = {
        "SteamCMDPath": "",
        "DestinationFolder": "",
        "continuous_download": "on",
        "clean_on_finish": "on",
        "skip_already_installed": "on",
        "use_steam_creds": "off",
        "GameExecutable": "BlackOps3",
        "LaunchParameters": "",
    }

    with CONFIG_FILE_PATH.open("w", encoding="utf-8") as config_file:
        config.write(config_file)


def load_config() -> configparser.ConfigParser:
    ensure_config_file()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE_PATH, encoding="utf-8")
    if "Settings" not in config:
        config["Settings"] = {}
    return config


def get_setting(name: str, fallback: str = "") -> str:
    config = load_config()
    return config.get("Settings", name, fallback=fallback)


def save_settings(pairs: Dict[str, str]) -> None:
    config = load_config()
    for key, value in pairs.items():
        config.set("Settings", key, value)
    with CONFIG_FILE_PATH.open("w", encoding="utf-8") as config_file:
        config.write(config_file)


def extract_workshop_id(value: str) -> Optional[str]:
    value = value.strip()
    if value.isdigit():
        return value
    match = re.search(r"id=(\d+)", value)
    if match:
        return match.group(1)
    return None


def to_int(value: Optional[object]) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return 0
        if cleaned.isdigit() or (cleaned.startswith("-") and cleaned[1:].isdigit()):
            return int(cleaned)
        try:
            return int(float(cleaned))
        except ValueError:
            return 0
    return 0


def convert_bytes_to_readable(size_in_bytes: Optional[object]) -> str:
    total_bytes = to_int(size_in_bytes)
    if total_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    value = float(total_bytes)
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.2f} {units[index]}"


def format_speed(bytes_per_second: float) -> str:
    if bytes_per_second <= 0:
        return "0 B/s"
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    index = 0
    value = float(bytes_per_second)
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.2f} {units[index]}"


def request_workshop_details(workshop_id: str) -> Dict[str, object]:
    response = requests.post(
        ITEM_INFO_API,
        data={
            "itemcount": 1,
            "publishedfileids[0]": int(workshop_id),
        },
        timeout=30,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Steam Workshop returned invalid JSON") from exc
    details = payload.get("response", {}).get("publishedfiledetails", [])
    if not details or details[0].get("result") != 1:
        raise ValueError("Steam Workshop returned an unexpected response")
    return details[0]


def sanitize_description(raw: Optional[str]) -> str:
    if not raw:
        return ""
    text = re.sub(r"\[/?[a-zA-Z0-9=:_\-]+\]", "", raw)
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def get_workshop_file_size(workshop_id: str) -> Optional[int]:
    try:
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}&searchtext="
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        size_elements = soup.select(".detailsStatsContainerRight .detailsStatRight")
        if not size_elements:
            return None
        file_size_text = size_elements[0].get_text(strip=True).replace(",", "")
        match = re.match(r"([0-9.]+)\s*(B|KB|MB|GB)", file_size_text, re.IGNORECASE)
        if not match:
            return None
        value, unit = match.groups()
        value = float(value)
        unit = unit.upper()
        factors = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}
        return int(value * factors[unit])
    except Exception:
        return None


def get_folder_size(path: Path) -> int:
    size = 0
    for root, _, files in os.walk(path):
        for file_name in files:
            file_path = Path(root) / file_name
            if file_path.exists():
                size += file_path.stat().st_size
    return size


def normalize_timestamp(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(int(value)).isoformat()
        if isinstance(value, str) and value.isdigit():
            return datetime.utcfromtimestamp(int(value)).isoformat()
    except (OverflowError, OSError, ValueError):
        return None
    if isinstance(value, str):
        return value
    return None


def find_local_workshop_entry(workshop_id: str) -> Optional[Dict[str, object]]:
    workshop_id = str(workshop_id)
    destination = Path(get_setting("DestinationFolder", "")).expanduser()
    if not destination.exists():
        return None

    for entry in list_library_items(destination):
        if entry["id"] == workshop_id or entry["folder_name"].lower() == workshop_id.lower():
            metadata_path = Path(entry["path"]) / "zone" / "workshop.json"
            metadata = read_workshop_json(metadata_path) or {}
            return {
                "library": entry,
                "metadata": metadata,
                "workshop_json_path": str(metadata_path),
            }
    return None


def compose_workshop_info(workshop_id: str, steam_details: Optional[Dict[str, object]], local_entry: Optional[Dict[str, object]]) -> Dict[str, object]:
    info: Dict[str, object] = {"id": workshop_id}
    sources: List[str] = []

    if steam_details:
        sources.append("steam")
        size_bytes = steam_details.get("file_size") or get_workshop_file_size(workshop_id) or 0
        info.update(
            {
                "title": steam_details.get("title") or workshop_id,
                "description": sanitize_description(steam_details.get("description")),
                "preview_url": steam_details.get("preview_url"),
                "file_size_bytes": size_bytes,
                "file_size": convert_bytes_to_readable(size_bytes) if size_bytes else "Unknown",
                "tags": [tag.get("tag") for tag in steam_details.get("tags", []) if tag.get("tag")],
                "creator_id": steam_details.get("creator"),
                "created": normalize_timestamp(steam_details.get("time_created")),
                "updated": normalize_timestamp(steam_details.get("time_updated")),
                "workshop_url": WORKSHOP_URL.format(id=workshop_id),
                "views": steam_details.get("views"),
                "favorites": steam_details.get("favorited"),
                "subscriptions": steam_details.get("subscriptions"),
                "lifetime_subscriptions": steam_details.get("lifetime_subscriptions"),
                "type": steam_details.get("consumer_app_id"),
            }
        )

    if local_entry:
        sources.append("local")
        library_entry = local_entry.get("library", {})
        metadata = local_entry.get("metadata", {})

        info.setdefault("title", metadata.get("Title") or library_entry.get("name") or library_entry.get("folder_name"))
        description_local = metadata.get("Description") or library_entry.get("description")
        if description_local:
            info.setdefault("description", sanitize_description(description_local))

        preview_candidates = [
            metadata.get("PreviewImage"),
            metadata.get("PreviewURL"),
            metadata.get("PreviewUrl"),
        ]
        for candidate in preview_candidates:
            if candidate:
                info.setdefault("preview_url", candidate)
                break

        local_file_size_bytes = metadata.get("FileSize")
        if isinstance(local_file_size_bytes, str) and local_file_size_bytes.isdigit():
            local_file_size_bytes = int(local_file_size_bytes)
        if isinstance(local_file_size_bytes, (int, float)):
            info.setdefault("file_size_bytes", int(local_file_size_bytes))
            info.setdefault("file_size", convert_bytes_to_readable(int(local_file_size_bytes)))
        info.setdefault("file_size", library_entry.get("size"))

        tags_local = metadata.get("Tags")
        if isinstance(tags_local, list):
            existing_tags = set(info.get("tags", []) or [])
            existing_tags.update(tag for tag in tags_local if isinstance(tag, str))
            info["tags"] = sorted(existing_tags)

        info.setdefault("creator_id", metadata.get("CreatorID") or metadata.get("Creator"))
        info.setdefault("created", normalize_timestamp(metadata.get("TimeCreated")))
        info.setdefault("updated", normalize_timestamp(metadata.get("TimeUpdated")))
        if library_entry.get("id", "").isdigit():
            info.setdefault("workshop_url", WORKSHOP_URL.format(id=library_entry["id"]))

        info.update(
            {
                "folder_name": library_entry.get("folder_name"),
                "local_path": library_entry.get("path"),
                "type": library_entry.get("type", info.get("type")),
                "size_on_disk": library_entry.get("size"),
                "needs_fix": library_entry.get("needs_fix"),
            }
        )

    info["source"] = "+".join(sources) if sources else "unknown"
    return info


def read_workshop_json(json_path: Path) -> Optional[Dict[str, object]]:
    if not json_path.exists():
        return None
    try:
        with json_path.open("r", encoding="utf-8") as json_file:
            return json.load(json_file)
    except json.JSONDecodeError:
        return None


def list_library_items(destination_folder: Path) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []

    def collect(base_path: Path, entry_type: str) -> None:
        if not base_path.exists():
            return
        for directory in sorted(p for p in base_path.iterdir() if p.is_dir()):
            zone_path = directory / "zone"
            workshop_json = zone_path / "workshop.json"
            metadata = read_workshop_json(workshop_json)
            if not metadata:
                continue
            publisher_id = str(metadata.get("PublisherID", directory.name))
            folder_name_expected = metadata.get("FolderName", directory.name)
            title = metadata.get("Title") or directory.name
            description = metadata.get("Description") or ""
            size_bytes = get_folder_size(directory)
            needs_fix = directory.name.isdigit() and folder_name_expected and directory.name != folder_name_expected

            items.append(
                {
                    "id": publisher_id,
                    "name": title,
                    "folder_name": directory.name,
                    "expected_folder": folder_name_expected,
                    "type": entry_type,
                    "size": convert_bytes_to_readable(size_bytes),
                    "path": str(directory),
                    "needs_fix": bool(needs_fix),
                    "description": sanitize_description(description),
                }
            )

    collect(destination_folder / "usermaps", "Map")
    collect(destination_folder / "mods", "Mod")
    return items


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    shutil.rmtree(path, ignore_errors=True)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass
class DownloadResult:
    success: bool
    message: str


class DownloadManager:
    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.queue_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.process: Optional[subprocess.Popen] = None
        self.current_mode: Optional[str] = None  # "single" or "queue"

    def _update_state(self, **kwargs: object) -> None:
        app_state.update(kwargs)
        app_state["last_update"] = time.time()

    def is_busy(self) -> bool:
        running = self.thread and self.thread.is_alive()
        queued = self.queue_thread and self.queue_thread.is_alive()
        return bool(running or queued)

    def start_download(self, workshop_id: str) -> Tuple[bool, Optional[str]]:
        with self.lock:
            if self.is_busy():
                return False, "Another download is already running"
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run_download, args=(workshop_id,), daemon=True)
            self.thread.start()
            self.current_mode = "single"
            return True, None

    def stop(self) -> None:
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass

    def enqueue(self, items: List[str]) -> List[str]:
        added: List[str] = []
        for item in items:
            if item not in app_state["queue"]:
                app_state["queue"].append(item)
                added.append(item)
        return added

    def start_queue(self) -> Tuple[bool, Optional[str]]:
        with self.lock:
            if self.is_busy():
                return False, "A download is already running"
            if not app_state["queue"]:
                return False, "The queue is empty"
            self.stop_event.clear()
            self.queue_thread = threading.Thread(target=self._process_queue, daemon=True)
            self.queue_thread.start()
            self.current_mode = "queue"
            return True, None

    def _process_queue(self) -> None:
        while app_state["queue"] and not self.stop_event.is_set():
            next_id = app_state["queue"][0]
            result = self._perform_download(next_id)
            if not result.success and self.current_mode == "queue":
                # keep the failing item in the queue but move on
                app_state["queue"].pop(0)
                break
            app_state["queue"].pop(0)
        self._update_state(downloading=False, current_download=None, current_title="", download_speed="0 B/s")
        self.current_mode = None

    def _run_download(self, workshop_id: str) -> None:
        self._perform_download(workshop_id)
        self._update_state(downloading=False, current_download=None, current_title="", download_speed="0 B/s")
        self.current_mode = None

    def _perform_download(self, workshop_id: str) -> DownloadResult:
        workshop_id = workshop_id.strip()
        self._update_state(
            download_status="preparing",
            download_progress=0,
            status_message="Preparing download...",
            current_download=workshop_id,
            current_title="",
            downloading=True,
            file_size="Unknown",
            download_speed="0 B/s",
            progress_samples=[],
        )

        destination_raw = get_setting("DestinationFolder", "").strip()
        steamcmd_raw = get_setting("SteamCMDPath", "").strip()

        if not destination_raw:
            self._update_state(download_status="error", status_message="Destination folder is not set", downloading=False)
            return DownloadResult(False, "Destination folder is not set")
        if not steamcmd_raw:
            self._update_state(download_status="error", status_message="SteamCMD path is not set", downloading=False)
            return DownloadResult(False, "SteamCMD path is not set")

        destination_folder = Path(destination_raw).expanduser()
        steamcmd_path = Path(steamcmd_raw).expanduser()

        if not workshop_id.isdigit():
            extracted = extract_workshop_id(workshop_id)
            if not extracted:
                self._update_state(download_status="error", status_message="Invalid Workshop ID")
                return DownloadResult(False, "Invalid Workshop ID")
            workshop_id = extracted

        if not destination_folder.exists():
            self._update_state(download_status="error", status_message="Destination folder does not exist", downloading=False)
            return DownloadResult(False, "Destination folder does not exist")

        if steamcmd_path.is_file():
            if steamcmd_path.name.lower() != "steamcmd.exe":
                message = f"Invalid SteamCMD executable: {steamcmd_path.name}"
                self._update_state(download_status="error", status_message=message, downloading=False)
                return DownloadResult(False, message)
            steamcmd_exe = steamcmd_path
            steamcmd_path = steamcmd_path.parent
        else:
            steamcmd_exe = steamcmd_path / "steamcmd.exe"

        if not steamcmd_path.exists():
            message = f"SteamCMD path does not exist: {steamcmd_path}"
            self._update_state(download_status="error", status_message=message, downloading=False)
            return DownloadResult(False, message)

        if not steamcmd_exe.exists():
            message = f"steamcmd.exe not found in {steamcmd_path}"
            self._update_state(download_status="error", status_message=message, downloading=False)
            return DownloadResult(False, "SteamCMD was not found")

        try:
            details = request_workshop_details(workshop_id)
        except Exception as exc:
            self._update_state(download_status="error", status_message=str(exc), downloading=False)
            return DownloadResult(False, str(exc))

        item_title = details.get("title") or workshop_id
        file_size_bytes = to_int(details.get("file_size"))
        if not file_size_bytes:
            file_size_bytes = to_int(get_workshop_file_size(workshop_id))

        self._update_state(
            downloading=True,
            current_download=workshop_id,
            current_title=item_title,
            download_status="downloading",
            file_size=convert_bytes_to_readable(file_size_bytes) if file_size_bytes else "Unknown",
            status_message="Downloading from Steam Workshop...",
        )

        workshop_download_path = steamcmd_path / "steamapps" / "workshop" / "downloads" / STEAM_APP_ID / workshop_id
        workshop_content_path = steamcmd_path / "steamapps" / "workshop" / "content" / STEAM_APP_ID / workshop_id
        ensure_directory(workshop_download_path)
        baseline_download_bytes = get_folder_size(workshop_download_path)
        baseline_content_bytes = get_folder_size(workshop_content_path) if workshop_content_path.exists() else 0

        command = [
            str(steamcmd_exe),
            "+login",
            "anonymous",
            "app_update",
            STEAM_APP_ID,
            "+workshop_download_item",
            STEAM_APP_ID,
            workshop_id,
            "validate",
            "+quit",
        ]

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(steamcmd_path),
            text=True,
            startupinfo=startupinfo,
        )

        previous_size = 0
        previous_time = time.time()
        size_samples: List[int] = []

        try:
            while self.process.poll() is None:
                if self.stop_event.is_set():
                    self.process.terminate()
                    self.process.wait(timeout=5)
                    self._update_state(
                        download_status="stopped",
                        status_message="Download cancelled by user",
                        downloading=False,
                        download_speed="0 B/s",
                    )
                    return DownloadResult(False, "Download stopped")

                time.sleep(1)
                download_bytes = 0
                content_bytes = 0
                if workshop_download_path.exists():
                    download_bytes = max(get_folder_size(workshop_download_path) - baseline_download_bytes, 0)
                if workshop_content_path.exists():
                    content_bytes = max(get_folder_size(workshop_content_path) - baseline_content_bytes, 0)
                total_bytes = download_bytes + content_bytes

                size_samples.append(total_bytes)
                if len(size_samples) > 60:
                    size_samples.pop(0)

                average_bytes = sum(size_samples[-5:]) // min(len(size_samples), 5)

                now = time.time()
                delta = total_bytes - previous_size
                elapsed = now - previous_time
                speed = format_speed(delta / elapsed) if elapsed > 0 else "0 B/s"

                previous_size = total_bytes
                previous_time = now

                progress = 0
                if file_size_bytes:
                    progress = min(int(average_bytes / file_size_bytes * 100), 100)

                current_progress = int(app_state.get("download_progress", 0))
                if progress < current_progress:
                    progress = current_progress
                if progress >= 100 and self.process.poll() is None:
                    progress = 99

                self._update_state(
                    download_progress=progress,
                    download_speed=speed,
                    status_message="Downloading from Steam Workshop...",
                )

            return_code = self.process.wait()
            if return_code != 0:
                self._update_state(download_status="error", status_message="SteamCMD failed to download the item", downloading=False)
                return DownloadResult(False, "SteamCMD failed to download the item")

            self._update_state(status_message="Finalizing download...")

            # Wait until workshop.json appears
            workshop_json = workshop_content_path / "workshop.json"
            waited = 0
            max_wait = 120
            while not workshop_json.exists() and waited < max_wait and not self.stop_event.is_set():
                if workshop_content_path.exists() and any(workshop_content_path.iterdir()):
                    time.sleep(2)
                    waited += 2
                    continue
                time.sleep(1)
                waited += 1
            if not workshop_json.exists():
                candidates = list(workshop_content_path.rglob("workshop.json")) if workshop_content_path.exists() else []
                if not candidates and workshop_download_path.exists():
                    candidates = list(workshop_download_path.rglob("workshop.json"))
                if candidates:
                    workshop_json = candidates[0]
                else:
                    message = "workshop.json was not produced by SteamCMD"
                    self._update_state(download_status="error", status_message=message, downloading=False)
                    return DownloadResult(False, message)

            if workshop_content_path.exists() and workshop_json.is_relative_to(workshop_content_path):
                source_root = workshop_content_path
            else:
                source_root = workshop_json.parent

            metadata = read_workshop_json(workshop_json)
            if not metadata:
                message = "Unable to read workshop.json"
                self._update_state(download_status="error", status_message=message, downloading=False)
                return DownloadResult(False, message)

            folder_name = metadata.get("FolderName") or metadata.get("PublisherID") or workshop_id
            item_type = (metadata.get("Type") or "map").lower()
            destination_base = destination_folder / ("usermaps" if item_type == "map" else "mods")
            ensure_directory(destination_base)

            final_folder = destination_base / str(folder_name)
            attempts = 0
            while final_folder.exists() and attempts < 10 and final_folder.name != folder_name:
                attempts += 1
                final_folder = destination_base / f"{folder_name}_{workshop_id}_{attempts}"

            zone_folder = final_folder / "zone"
            ensure_directory(zone_folder)

            self._update_state(download_status="installing", status_message="Installing into game folder...")
            shutil.copytree(source_root, zone_folder, dirs_exist_ok=True)

            if get_setting("clean_on_finish", "on").lower() == "on":
                remove_tree(workshop_download_path)
                remove_tree(workshop_content_path)

            self._update_state(
                download_status="completed",
                download_progress=100,
                download_speed="0 B/s",
                status_message="Download completed successfully",
                downloading=False,
            )

            app_state["library_items"] = load_library_if_available()
            return DownloadResult(True, "Download completed")

        except Exception as exc:  # pragma: no cover - broad safety net
            self._update_state(download_status="error", status_message=str(exc), downloading=False)
            return DownloadResult(False, str(exc))
        finally:
            self.process = None


app = Flask(__name__)
CORS(app)

app_state: Dict[str, object] = {
    "download_progress": 0,
    "download_status": "idle",
    "current_download": None,
    "current_title": "",
    "queue": [],
    "library_items": [],
    "downloading": False,
    "download_speed": "0 B/s",
    "file_size": "0 B",
    "status_message": "",
    "last_update": time.time(),
}

download_manager = DownloadManager()


def load_library_if_available() -> List[Dict[str, object]]:
    destination = Path(get_setting("DestinationFolder", "")).expanduser()
    if not destination.exists():
        return []
    return list_library_items(destination)


@app.route("/api/health", methods=["GET"])
def health_check() -> object:
    return jsonify({
        "status": "healthy",
        "message": "BOIIIWD API is running",
        "timestamp": time.time(),
    })


@app.route("/api/library", methods=["GET"])
def get_library() -> object:
    app_state["library_items"] = load_library_if_available()
    return jsonify({
        "items": app_state["library_items"],
        "count": len(app_state["library_items"]),
    })


@app.route("/api/library/fix-compatibility", methods=["POST"])
def fix_bo3_enhanced_compatibility() -> object:
    payload = request.get_json(force=True)
    items = payload.get("items", [])

    destination = Path(get_setting("DestinationFolder", "")).expanduser()
    usermaps_dir = destination / "usermaps"
    if not usermaps_dir.exists():
        return jsonify({"success": False, "message": "usermaps folder not found"}), 400

    if items == "all" or (isinstance(items, list) and "all" in items):
        target_ids = None
    else:
        target_ids = {str(item) for item in items}

    fixed: List[Dict[str, object]] = []
    errors: List[str] = []

    for entry in sorted(p for p in usermaps_dir.iterdir() if p.is_dir()):
        metadata = read_workshop_json(entry / "zone" / "workshop.json")
        if not metadata:
            continue
        publisher_id = str(metadata.get("PublisherID", entry.name))
        if target_ids is not None and publisher_id not in target_ids:
            continue

        expected_folder = metadata.get("FolderName")
        if not expected_folder or expected_folder == entry.name:
            continue

        target_path = usermaps_dir / expected_folder
        suffix = 0
        while target_path.exists() and target_path != entry:
            suffix += 1
            target_path = usermaps_dir / f"{expected_folder}_{suffix}"

        try:
            entry.rename(target_path)
            fixed.append(
                {
                    "id": publisher_id,
                    "old_name": entry.name,
                    "new_name": target_path.name,
                    "type": metadata.get("Type", "map"),
                }
            )
        except Exception as exc:
            errors.append(f"Failed to rename {entry.name}: {exc}")

    app_state["library_items"] = load_library_if_available()

    return jsonify(
        {
            "success": True,
            "message": f"{len(fixed)} items renamed",
            "fixed_items": fixed,
            "errors": errors,
            "fixed_count": len(fixed),
            "error_count": len(errors),
        }
    )


@app.route("/api/workshop/info", methods=["GET"])
def get_workshop_info() -> object:
    workshop_raw = request.args.get("id", "").strip()
    if not workshop_raw:
        return jsonify({"success": False, "message": "Workshop ID is required"}), 400

    extracted = extract_workshop_id(workshop_raw)
    lookup_id = str(extracted or workshop_raw)
    local_entry = find_local_workshop_entry(lookup_id)

    if extracted:
        try:
            details = request_workshop_details(extracted)
            info = compose_workshop_info(extracted, details, local_entry)
            return jsonify({"success": True, "info": info})
        except Exception as exc:
            if local_entry:
                info = compose_workshop_info(lookup_id, None, local_entry)
                info["steam_error"] = str(exc)
                return jsonify({"success": True, "info": info, "warning": str(exc)})
            return jsonify({"success": False, "message": str(exc)}), 502

    if local_entry:
        info = compose_workshop_info(lookup_id, None, local_entry)
        return jsonify({"success": True, "info": info})

    return jsonify({"success": False, "message": "Invalid Workshop ID"}), 400


@app.route("/api/download", methods=["POST"])
def download_workshop_item() -> object:
    payload = request.get_json(force=True)
    workshop_id = payload.get("workshop_id", "")
    if not workshop_id:
        return jsonify({"success": False, "message": "Workshop ID is required"}), 400

    started, error = download_manager.start_download(workshop_id)
    if not started:
        return jsonify({"success": False, "message": error}), 409

    return jsonify({"success": True, "message": "Download started", "workshop_id": workshop_id})


@app.route("/api/download/stop", methods=["POST"])
def stop_download() -> object:
    download_manager.stop()
    return jsonify({"success": True, "message": "Download stop requested"})


@app.route("/api/download/status", methods=["GET"])
def download_status() -> object:
    return jsonify(
        {
            "downloading": download_manager.is_busy(),
            "progress": app_state["download_progress"],
            "status": app_state["download_status"],
            "current_download": app_state["current_download"],
            "title": app_state["current_title"],
            "speed": app_state["download_speed"],
            "file_size": app_state["file_size"],
            "message": app_state["status_message"],
        }
    )


@app.route("/api/queue", methods=["GET"])
def get_queue() -> object:
    return jsonify({"queue": app_state["queue"], "count": len(app_state["queue"])})


@app.route("/api/queue", methods=["POST"])
def add_to_queue() -> object:
    payload = request.get_json(force=True)
    raw_items = payload.get("items", [])
    if isinstance(raw_items, str):
        raw_items = [part.strip() for part in re.split(r"[\n,]", raw_items) if part.strip()]

    cleaned: List[str] = []
    for item in raw_items:
        extracted = extract_workshop_id(item)
        if extracted:
            cleaned.append(extracted)

    added = download_manager.enqueue(cleaned)
    return jsonify({
        "success": True,
        "added_items": added,
        "queue": app_state["queue"],
        "count": len(app_state["queue"]),
    })


@app.route("/api/queue", methods=["DELETE"])
def clear_queue() -> object:
    app_state["queue"].clear()
    return jsonify({"success": True, "message": "Queue cleared", "queue": app_state["queue"]})


@app.route("/api/queue/process", methods=["POST"])
def process_queue() -> object:
    started, error = download_manager.start_queue()
    if not started:
        return jsonify({"success": False, "message": error}), 409
    return jsonify({"success": True, "message": "Queue processing started"})


@app.route("/api/queue/<item_id>", methods=["DELETE"])
def remove_from_queue(item_id: str) -> object:
    item_id = extract_workshop_id(item_id) or item_id
    if item_id in app_state["queue"]:
        app_state["queue"].remove(item_id)
        return jsonify({"success": True, "message": "Item removed", "queue": app_state["queue"]})
    return jsonify({"success": False, "message": "Item not found in queue"}), 404


@app.route("/api/settings", methods=["GET"])
def get_settings() -> object:
    config = load_config()
    section = config["Settings"]
    settings = {
        "destination_folder": section.get("DestinationFolder", ""),
        "steamcmd_path": section.get("SteamCMDPath", ""),
        "game_executable": section.get("GameExecutable", "BlackOps3"),
        "launch_parameters": section.get("LaunchParameters", ""),
        "appearance": section.get("appearance", "Dark"),
        "scaling": section.get("scaling", "1.0"),
        "continuous_download": section.get("continuous_download", "on"),
        "clean_on_finish": section.get("clean_on_finish", "on"),
        "skip_already_installed": section.get("skip_already_installed", "on"),
        "console": section.get("console", "off"),
        "estimated_progress": section.get("estimated_progress", "on"),
        "use_steam_creds": section.get("use_steam_creds", "off"),
    }
    return jsonify({"success": True, "settings": settings})


@app.route("/api/settings", methods=["POST"])
def save_settings_endpoint() -> object:
    payload = request.get_json(force=True)
    settings = payload.get("settings", {})
    mapping = {
        "destination_folder": "DestinationFolder",
        "steamcmd_path": "SteamCMDPath",
        "game_executable": "GameExecutable",
        "launch_parameters": "LaunchParameters",
        "appearance": "appearance",
        "scaling": "scaling",
        "continuous_download": "continuous_download",
        "clean_on_finish": "clean_on_finish",
        "skip_already_installed": "skip_already_installed",
        "console": "console",
        "estimated_progress": "estimated_progress",
        "use_steam_creds": "use_steam_creds",
    }

    normalized: Dict[str, str] = {}
    for key, value in settings.items():
        config_key = mapping.get(key, key)
        normalized[config_key] = str(value)

    save_settings(normalized)
    return jsonify({"success": True, "message": "Settings saved"})


@app.route("/api/library/remove", methods=["DELETE"])
def remove_library_item() -> object:
    payload = request.get_json(force=True)
    item_id = payload.get("item_id", "")
    item_id = extract_workshop_id(item_id) or item_id

    destination = Path(get_setting("DestinationFolder", "")).expanduser()
    removed = False
    for base in (destination / "usermaps", destination / "mods"):
        if not base.exists():
            continue
        for entry in base.iterdir():
            metadata = read_workshop_json(entry / "zone" / "workshop.json")
            publisher_id = str(metadata.get("PublisherID", entry.name)) if metadata else entry.name
            if publisher_id == item_id:
                remove_tree(entry)
                removed = True
                break
        if removed:
            break

    if removed:
        app_state["library_items"] = load_library_if_available()
        return jsonify({"success": True, "message": "Item removed"})
    return jsonify({"success": False, "message": "Item not found"}), 404


@app.route("/api/game/launch", methods=["POST"])
def launch_game() -> object:
    destination = Path(get_setting("DestinationFolder", "")).expanduser()
    if not destination.exists():
        return jsonify({"success": False, "message": "Destination folder not configured"}), 400

    executable = get_setting("GameExecutable", "BlackOps3").strip() or "BlackOps3"
    if not executable.lower().endswith(".exe"):
        executable += ".exe"
    launch_parameters = get_setting("LaunchParameters", "").strip()
    exe_path = destination / executable
    if not exe_path.exists():
        return jsonify({"success": False, "message": "Game executable not found"}), 404

    try:
        args = [str(exe_path)]
        if launch_parameters:
            args.extend(launch_parameters.split())
        subprocess.Popen(args, cwd=str(destination))
        return jsonify({"success": True, "message": "Game launched"})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/api/workshop/browse", methods=["POST", "GET"])
def browse_workshop() -> object:
    game_id = request.args.get("game_id") or request.json.get("game_id") if request.is_json else STEAM_APP_ID
    url = f"https://steamcommunity.com/app/{game_id}/workshop/"
    return jsonify({"success": True, "workshop_url": url})


if __name__ == "__main__":
    app_state["library_items"] = load_library_if_available()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)