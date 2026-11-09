import csv
import os
import re
from pathlib import Path
from difflib import SequenceMatcher


class PhraseDatabase:
    def __init__(self, db_dir="podcast_db"):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(exist_ok=True)
        self.catalog_path = self.db_dir / "catalog.csv"
        self._init_catalog()

    def _init_catalog(self):
        """Initialize CSV catalog if it doesn't exist."""
        if not self.catalog_path.exists():
            with open(self.catalog_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "clip", "speaker", "phrase",
                    "start", "end", "duration", "source_video"
                ])

    def add_clip(self, clip_path, speaker, phrase, start, end, source_video):
        """Add a clip entry to the catalog."""
        duration = round(end - start, 2)
        rel_path = os.path.relpath(clip_path, self.db_dir)

        with open(self.catalog_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                rel_path, speaker, phrase.lower().strip(),
                round(start, 2), round(end, 2), duration, source_video
            ])

    def search_phrase(self, phrase):
        """Search for exact phrase match."""
        phrase = phrase.lower().strip()
        results = []
        if not self.catalog_path.exists():
            return results
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if phrase == row["phrase"]:
                    results.append(row)
        return results

    def search_word(self, word):
        """Search for clips containing a specific word."""
        word = word.lower().strip()
        results = []
        if not self.catalog_path.exists():
            return results
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if word in row["phrase"].split():
                    results.append(row)
        return results

    def fuzzy_search(self, text, threshold=0.6):
        """Fuzzy search for similar phrases."""
        text = text.lower().strip()
        results = []
        if not self.catalog_path.exists():
            return results
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ratio = SequenceMatcher(None, text, row["phrase"]).ratio()
                if ratio >= threshold:
                    results.append({**row, "similarity": ratio})
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results

    def get_clips_for_speaker(self, speaker):
        """Get all clips for a specific speaker."""
        clips = []
        if not self.catalog_path.exists():
            return clips
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["speaker"] == speaker:
                    clips.append(row)
        return clips

    def get_all_speakers(self):
        """Get list of all speakers."""
        speakers = set()
        if not self.catalog_path.exists():
            return list(speakers)
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                speakers.add(row["speaker"])
        return sorted(list(speakers))

    def get_stats(self):
        """Get database statistics."""
        if not self.catalog_path.exists():
            return {"total_clips": 0, "speakers": []}
        speakers = set()
        total = 0
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                speakers.add(row["speaker"])
        return {
            "total_clips": total,
            "speakers": sorted(list(speakers))
        }

    def remove_speaker(self, speaker):
        """Remove all clips for a specific speaker."""
        if not self.catalog_path.exists():
            return
        rows = []
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row["speaker"] != speaker:
                    rows.append(row)
                else:
                    clip_path = self.db_dir / row["clip"]
                    if clip_path.exists():
                        clip_path.unlink()
        with open(self.catalog_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def clear_database(self):
        """Clear the entire database."""
        for speaker_dir in self.db_dir.rglob("*"):
            if speaker_dir.is_dir():
                for clip in speaker_dir.glob("*.mp4"):
                    clip.unlink()
        self._init_catalog()
