import os
import subprocess
import json
import cv2
import numpy as np
from pathlib import Path
import imageio_ffmpeg


class VideoProcessor:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def get_video_duration(self, video_path):
        """Get video duration in seconds."""
        cmd = [
            self.ffmpeg,
            "-i", video_path,
            "-show_entries", "format=duration",
            "-v", "quiet",
            "-of", "csv=p=0"
        ]
        result = subprocess.run(
            [self.ffmpeg, "-i", video_path],
            capture_output=True, text=True
        )
        for line in result.stderr.split("\n"):
            if "Duration" in line:
                parts = line.split("Duration: ")[1].split(",")[0].split(":")
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        return 0

    def clip_video(self, video_path, start_seconds, end_seconds, output_name, format_type="landscape"):
        """Clip a video segment and optionally convert to portrait format."""
        duration = end_seconds - start_seconds
        output_path = self.output_dir / f"{output_name}.mp4"

        if format_type == "portrait":
            # First detect face position for centering
            face_center_x = self._detect_face_center(video_path, start_seconds, end_seconds)

            # Create portrait (9:16) with face centered
            w, h = 1080, 1920  # 9:16 portrait
            output_path = self.output_dir / f"{output_name}_portrait.mp4"

            # Calculate crop to center on face
            # Original video is 16:9 typically (1920x1080)
            # We need to crop a 1080x1920 section centered on the face
            # Since original is wider than tall, we crop width and scale up

            if face_center_x is not None:
                # Center crop on face
                crop_filter = (
                    f"crop=ih*9/16:ih:(iw*{face_center_x}-ih*9/16/2):0,"
                    f"scale={w}:{h}:flags=lanczos"
                )
            else:
                # Default center crop
                crop_filter = (
                    f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
                    f"scale={w}:{h}:flags=lanczos"
                )

            cmd = [
                self.ffmpeg, "-y",
                "-ss", str(start_seconds),
                "-i", video_path,
                "-t", str(duration),
                "-vf", crop_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path)
            ]
        else:
            # Landscape (16:9) - keep original or standardize to 1920x1080
            output_path = self.output_dir / f"{output_name}_landscape.mp4"
            w, h = 1920, 1080

            cmd = [
                self.ffmpeg, "-y",
                "-ss", str(start_seconds),
                "-i", video_path,
                "-t", str(duration),
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path)
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr}")

        return str(output_path)

    def _detect_face_center(self, video_path, start_time, end_time, sample_count=5):
        """Detect face position in video segment and return normalized center X (0-1)."""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps else 0

        if duration == 0:
            cap.release()
            return None

        # Sample frames across the segment
        face_positions = []
        sample_points = np.linspace(start_time, end_time, sample_count)

        for t in sample_points:
            frame_num = int(t * fps)
            if frame_num >= total_frames:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50)
            )

            if len(faces) > 0:
                # Use the largest face
                largest = max(faces, key=lambda f: f[2] * f[3])
                x, y, w, h = largest
                center_x = (x + w / 2) / frame.shape[1]  # Normalize to 0-1
                face_positions.append(center_x)

        cap.release()

        if face_positions:
            return np.mean(face_positions)
        return None

    def process_all_clips(self, video_path, clips, progress_callback=None):
        """Process all clips in both landscape and portrait formats."""
        results = []

        for i, clip in enumerate(clips):
            title = clip.get("title", f"clip_{i+1}")
            # Sanitize filename
            safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
            safe_title = safe_title.strip()[:50]

            start = clip.get("start_seconds", 0)
            end = clip.get("end_seconds", 0)

            if start >= end:
                continue

            if progress_callback:
                progress_callback(f"Processing clip {i+1}/{len(clips)}: {title}")

            try:
                # Landscape version
                landscape_path = self.clip_video(
                    video_path, start, end, safe_title, "landscape"
                )

                # Portrait version with face centering
                portrait_path = self.clip_video(
                    video_path, start, end, safe_title, "portrait"
                )

                results.append({
                    "title": title,
                    "description": clip.get("description", ""),
                    "hook": clip.get("hook", ""),
                    "social_score": clip.get("social_score", 0),
                    "start_time": clip.get("start_time", ""),
                    "end_time": clip.get("end_time", ""),
                    "landscape": landscape_path,
                    "portrait": portrait_path,
                })

                if progress_callback:
                    progress_callback(f"Done: {title}")

            except Exception as e:
                if progress_callback:
                    progress_callback(f"Error processing {title}: {str(e)}")

        return results
