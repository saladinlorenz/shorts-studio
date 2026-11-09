import os
import re
import subprocess
import cv2
import numpy as np
from pathlib import Path
import imageio_ffmpeg

from database import PhraseDatabase
from downloader import YouTubeDownloader


class Podcaster:
    def __init__(self, db_dir="podcast_db"):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(exist_ok=True)
        self.db = PhraseDatabase(db_dir)
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def add_video(self, url, speaker_name=None, progress_callback=None):
        """Download a video and add its phrases to the database."""
        dl = YouTubeDownloader(str(self.db_dir / "temp"))

        # Download video
        if progress_callback:
            progress_callback("Downloading video...")
        video_path, title = dl.download_video(url, progress_callback=progress_callback)

        # Use video title as speaker name if not provided
        if not speaker_name:
            speaker_name = self._clean_for_filename(title)

        # Download subtitles
        if progress_callback:
            progress_callback("Downloading subtitles...")
        srt_path = dl.download_subtitles(url, progress_callback=progress_callback)

        if not srt_path:
            if progress_callback:
                progress_callback("No subtitles found - cannot split by phrases")
            return []

        # Detect face in video for speaker identity
        if progress_callback:
            progress_callback("Detecting speaker face...")
        face_embedding = self._detect_face_embedding(video_path)

        # Create speaker directory
        speaker_dir = self.db_dir / speaker_name
        speaker_dir.mkdir(exist_ok=True)

        # Save face embedding for this speaker
        if face_embedding is not None:
            np.save(speaker_dir / "face.npy", face_embedding)

        # Split video by phrases
        if progress_callback:
            progress_callback("Splitting video into phrases...")
        clips = self.split_video(video_path, srt_path, speaker_name, progress_callback=progress_callback)

        # Clean up temp files
        self._cleanup_temp()

        if progress_callback:
            progress_callback(f"Done! {len(clips)} clips added for {speaker_name}")

        return clips

    def split_video(self, video_path, srt_path, speaker, progress_callback=None):
        """Split a video into phrase clips based on SRT subtitles."""
        segments = self._parse_srt(srt_path)
        if not segments:
            if progress_callback:
                progress_callback("No subtitle segments found")
            return []

        clips_created = []

        for i, seg in enumerate(segments):
            if progress_callback:
                progress_callback(f"Clip {i+1}/{len(segments)}: {seg['text'][:40]}...")

            clean_text = self._clean_for_filename(seg["text"])
            if not clean_text or len(clean_text) < 2:
                continue

            clip_name = f"{clean_text}.mp4"
            clip_path = self.db_dir / clip_name

            # Skip if already exists
            if clip_path.exists():
                # Still add to catalog
                self.db.add_clip(
                    str(clip_path), speaker, seg["text"].lower(),
                    seg["start_seconds"], seg["end_seconds"],
                    os.path.basename(video_path)
                )
                clips_created.append(str(clip_path))
                continue

            # Cut the clip
            duration = seg["end_seconds"] - seg["start_seconds"]
            if duration < 0.3 or duration > 15:
                continue

            try:
                cmd = [
                    self.ffmpeg, "-y",
                    "-ss", str(seg["start_seconds"]),
                    "-i", video_path,
                    "-t", str(duration),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(clip_path)
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    continue

                # Add to database catalog
                self.db.add_clip(
                    str(clip_path), speaker, seg["text"].lower(),
                    seg["start_seconds"], seg["end_seconds"],
                    os.path.basename(video_path)
                )

                clips_created.append(str(clip_path))

            except Exception as e:
                if progress_callback:
                    progress_callback(f"Error: {str(e)}")

        if progress_callback:
            progress_callback(f"Created {len(clips_created)} clips")

        return clips_created

    def build_video(self, script_text, output_path=None, altern=True, progress_callback=None):
        """Build a video from a script with speaker alternation."""
        sentences = self._split_into_phrases(script_text)
        if not sentences:
            if progress_callback:
                progress_callback("No phrases to search")
            return None

        if progress_callback:
            progress_callback(f"Searching for {len(sentences)} phrases...")

        # Find ALL matching clips for each phrase (with speaker info)
        all_matches = []
        missing = []

        for i, phrase in enumerate(sentences):
            if progress_callback:
                progress_callback(f"Phrase {i+1}/{len(sentences)}: '{phrase[:30]}...'")

            matches = self._find_all_matches(phrase)
            if matches:
                all_matches.append({"phrase": phrase, "candidates": matches})
            else:
                missing.append(phrase)

        if missing:
            if progress_callback:
                progress_callback(f"Missing: {', '.join(missing[:5])}")

        if not all_matches:
            if progress_callback:
                progress_callback("No matching clips found")
            return None

        # Select clips with speaker alternation
        selected_clips = self._select_with_alternation(all_matches) if altern else [m["candidates"][0] for m in all_matches]

        if progress_callback:
            progress_callback(f"Found {len(selected_clips)}/{len(sentences)} clips. Assembling...")

        # Assemble video
        return self._assemble_clips(selected_clips, output_path, progress_callback)

    def _find_all_matches(self, phrase):
        """Find all matching clips for a phrase."""
        phrase_lower = phrase.lower().strip()

        # 1. Exact phrase match
        matches = self.db.search_phrase(phrase_lower)
        if matches:
            return matches

        # 2. Word search
        words = phrase_lower.split()
        if len(words) > 1:
            word_matches = []
            for word in words:
                m = self.db.search_word(word)
                if m:
                    word_matches.extend(m)
            if word_matches:
                return word_matches

        # 3. Fuzzy match
        return self.db.fuzzy_search(phrase_lower, threshold=0.5)

    def _select_with_alternation(self, all_matches):
        """Select clips alternating between different speakers."""
        selected = []
        last_speaker = None

        for group in all_matches:
            candidates = group["candidates"]

            # Try to pick a different speaker than the last one
            best = None
            for candidate in candidates:
                if last_speaker is None or candidate["speaker"] != last_speaker:
                    best = candidate
                    break

            # If no different speaker found, just pick the first
            if best is None:
                best = candidates[0]

            selected.append(best)
            last_speaker = best["speaker"]

        return selected

    def _split_into_phrases(self, text):
        """Split text into natural phrases/sentences."""
        phrases = re.split(r"[.!?\n]+", text)
        phrases = [p.strip() for p in phrases if p.strip()]
        return phrases

    def _assemble_clips(self, clips, output_path=None, progress_callback=None):
        """Assemble clips into a single video using FFmpeg concat."""
        if output_path is None:
            output_path = self.db_dir / "output" / "generated_video.mp4"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create concat list file
        concat_list = output_path.parent / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in clips:
                clip_path = clip["clip"]
                if not os.path.isabs(clip_path):
                    clip_path = str(self.db_dir / clip_path)
                clip_path = clip_path.replace("'", "'\\''")
                f.write(f"file '{clip_path}'\n")

        # Run FFmpeg concat
        cmd = [
            self.ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        concat_list.unlink(missing_ok=True)

        if result.returncode != 0:
            if progress_callback:
                progress_callback(f"FFmpeg error: {result.stderr[:200]}")
            return None

        if progress_callback:
            progress_callback(f"Video created: {output_path}")

        return str(output_path)

    def _detect_face_embedding(self, video_path, sample_count=3):
        """Detect face in video and return normalized embedding."""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames == 0:
            cap.release()
            return None

        # Sample frames
        sample_points = np.linspace(0, total_frames - 1, sample_count, dtype=int)

        for frame_num in sample_points:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
            )

            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2] * f[3])
                x, y, w, h = largest
                # Return normalized face region as simple embedding
                face_region = frame[y:y+h, x:x+w]
                if face_region.size > 0:
                    face_resized = cv2.resize(face_region, (100, 100))
                    cap.release()
                    return face_resized.mean(axis=(0, 1)) / 255.0

        cap.release()
        return None

    def _parse_srt(self, srt_path):
        """Parse SRT file into segments."""
        if not srt_path or not os.path.exists(srt_path):
            return []

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)"
        matches = re.findall(pattern, content, re.DOTALL)

        segments = []
        for idx, start, end, text in matches:
            clean_text = text.strip().replace("\n", " ")
            if clean_text:
                segments.append({
                    "index": int(idx),
                    "start": start,
                    "end": end,
                    "start_seconds": self._timestamp_to_seconds(start),
                    "end_seconds": self._timestamp_to_seconds(end),
                    "text": clean_text,
                })

        return segments

    def _timestamp_to_seconds(self, ts):
        """Convert SRT timestamp to seconds."""
        parts = ts.replace(",", ".").split(":")
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s

    def _clean_for_filename(self, text):
        """Clean text to be used as filename."""
        cleaned = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
        cleaned = cleaned.strip().replace(" ", "_")
        cleaned = cleaned[:60]
        return cleaned.lower()

    def _cleanup_temp(self):
        """Remove temporary download files."""
        temp_dir = self.db_dir / "temp"
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def get_stats(self):
        """Get database statistics."""
        return self.db.get_stats()
