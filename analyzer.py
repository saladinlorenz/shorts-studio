import json
from groq import Groq


class TranscriptAnalyzer:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)

    def analyze_transcript(self, transcript_text, video_title="Video", num_clips=5):
        """Analyze transcript to find important moments using Groq AI."""
        prompt = f"""Analyze this video transcript and identify the {num_clips} most important, 
engaging, or impactful moments. These should be moments that would make great short clips 
for social media (TikTok, Reels, Shorts).

Video Title: {video_title}

Transcript:
{transcript_text}

Return a JSON array with exactly this format for each important moment:
[
  {{
    "title": "Short catchy title for the clip",
    "description": "Brief description of why this moment is important",
    "start_time": "HH:MM:SS",
    "end_time": "HH:MM:SS",
    "start_seconds": 123.45,
    "end_seconds": 189.67,
    "hook": "A compelling hook sentence for the clip",
    "social_score": 85
  }}
]

Rules:
- Each clip should be 15-60 seconds long (ideal for social media)
- Focus on emotional peaks, funny moments, key insights, controversial takes, or dramatic moments
- Include the hook that would make someone stop scrolling
- social_score from 1-100 indicates how viral the clip could be
- Return ONLY valid JSON, no other text
- Make sure start_seconds and end_seconds match the start_time and end_time
- Ensure clips don't overlap too much"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )

        result_text = response.choices[0].message.content.strip()

        # Clean up response - remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

        try:
            clips = json.loads(result_text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re

            json_match = re.search(r"\[.*\]", result_text, re.DOTALL)
            if json_match:
                clips = json.loads(json_match.group())
            else:
                raise ValueError(f"Could not parse AI response as JSON:\n{result_text}")

        return clips

    def get_summary(self, transcript_text, video_title="Video"):
        """Get a brief summary of the video."""
        prompt = f"""Give a brief 2-3 sentence summary of this video:

Title: {video_title}
Transcript: {transcript_text[:3000]}

Summary:"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )

        return response.choices[0].message.content.strip()
