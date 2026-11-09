import os
import re
import json
import yt_dlp
from pathlib import Path


class YouTubeDownloader:
    def __init__(self, output_dir="downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def get_video_info(self, url):
        """Get video metadata without downloading."""
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "formats": info.get("formats", []),
                "subtitles": list(info.get("subtitles", {}).keys()),
                "auto_captions": list(info.get("automatic_captions", {}).keys()),
            }

    def download_video(self, url, progress_callback=None):
        """Download video with best quality."""
        video_path = None

        def progress_hook(d):
            nonlocal video_path
            if d["status"] == "downloading":
                if progress_callback:
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    downloaded = d.get("downloaded_bytes", 0)
                    pct = (downloaded / total * 100) if total else 0
                    progress_callback(f"Downloading: {pct:.1f}%")
            elif d["status"] == "finished":
                video_path = d["filename"]
                if progress_callback:
                    progress_callback("Download complete, processing...")

        ydl_opts = {
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "outtmpl": str(self.output_dir / "%(title)s.%(ext)s"),
            "progress_hooks": [progress_hook],
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Ensure .mp4 extension
            base = os.path.splitext(filename)[0]
            video_path = base + ".mp4"
            if not os.path.exists(video_path):
                video_path = filename

        return video_path, info.get("title", "video")

    def download_subtitles(self, url, progress_callback=None):
        """Download subtitles (auto-generated or manual)."""
        if progress_callback:
            progress_callback("Fetching subtitle info...")

        sub_path = None
        lang = "fr"  # Try French first

        # First try to get available subtitles info
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            available_subs = list(info.get("subtitles", {}).keys())
            auto_caps = list(info.get("automatic_captions", {}).keys())

            # Pick best language
            if lang in available_subs:
                sub_lang = lang
            elif lang in auto_caps:
                sub_lang = lang
            elif available_subs:
                sub_lang = available_subs[0]
            elif auto_caps:
                sub_lang = auto_caps[0]
            else:
                if progress_callback:
                    progress_callback("No subtitles found")
                return None

        # Download subtitles as SRT
        sub_dir = str(self.output_dir / "subs")
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [sub_lang],
            "sub-format": "srt",
            "outtmpl": str(self.output_dir / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        # Find the subtitle file
        for f in self.output_dir.iterdir():
            if f.suffix == ".srt" and title.replace(" ", "_") in f.name:
                sub_path = str(f)
                break
            if f.suffix == ".srt":
                sub_path = str(f)

        if progress_callback:
            progress_callback(f"Subtitles downloaded ({sub_lang})")

        return sub_path

    def srt_to_text(self, srt_path):
        """Convert SRT file to plain text with timestamps."""
        if not srt_path or not os.path.exists(srt_path):
            return "", []

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse SRT format
        pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)"
        matches = re.findall(pattern, content, re.DOTALL)

        segments = []
        full_text_parts = []

        for idx, start, end, text in matches:
            clean_text = text.strip().replace("\n", " ")
            if clean_text:
                segments.append(
                    {
                        "index": int(idx),
                        "start": start,
                        "end": end,
                        "start_seconds": self._timestamp_to_seconds(start),
                        "end_seconds": self._timestamp_to_seconds(end),
                        "text": clean_text,
                    }
                )
                full_text_parts.append(f"[{start} -> {end}] {clean_text}")

        return "\n".join(full_text_parts), segments

    def _timestamp_to_seconds(self, ts):
        """Convert SRT timestamp to seconds."""
        parts = ts.replace(",", ".").split(":")
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s

    def seconds_to_timestamp(self, seconds):
        """Convert seconds to HH:MM:SS format."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
