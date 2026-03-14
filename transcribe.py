"""
transcribe.py — Extract audio from video and transcribe with Whisper.

Usage:
    python transcribe.py <session-output-dir> [--model small]

Expects video.mp4 in the output dir; writes audio.mp3 and transcript.txt.
"""

import argparse
import os
from pathlib import Path


def extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract audio track from video file using ffmpeg."""
    if audio_path.exists():
        print(f"  audio.mp3 already exists, skipping extraction.")
        return

    import ffmpeg  # type: ignore

    print(f"Extracting audio from {video_path.name}...")
    (
        ffmpeg
        .input(str(video_path))
        .output(str(audio_path), q="0", map="a")
        .overwrite_output()
        .run(quiet=True)
    )
    size_mb = audio_path.stat().st_size / 1_048_576
    print(f"  Extracted audio.mp3 ({size_mb:.1f} MB)")


def transcribe(audio_path: Path, transcript_path: Path, model_name: str = "small") -> str:
    """Transcribe audio file with Whisper; returns transcript text."""
    if transcript_path.exists():
        print(f"  transcript.txt already exists, skipping transcription.")
        return transcript_path.read_text()

    import whisper  # type: ignore

    print(f"Loading Whisper model '{model_name}'...")
    model = whisper.load_model(model_name)

    print(f"Transcribing {audio_path.name} (this may take a while)...")
    result = model.transcribe(str(audio_path))
    text = result["text"]

    transcript_path.write_text(text)
    print(f"  Transcript saved ({len(text)} characters).")
    return text


def run(output_dir: Path, model_name: str | None = None) -> str:
    """Extract audio and transcribe; return transcript text."""
    model_name = model_name or os.environ.get("WHISPER_MODEL", "small")
    video_path = output_dir / "video.mp4"
    audio_path = output_dir / "audio.mp3"
    transcript_path = output_dir / "transcript.txt"

    if not video_path.exists():
        raise FileNotFoundError(f"No video.mp4 found in {output_dir}")

    extract_audio(video_path, audio_path)
    return transcribe(audio_path, transcript_path, model_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe session audio with Whisper.")
    parser.add_argument("output_dir", help="Session output directory containing video.mp4")
    parser.add_argument(
        "--model",
        default=None,
        help="Whisper model size (default: $WHISPER_MODEL or 'small')",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    run(Path(args.output_dir), model_name=args.model)


if __name__ == "__main__":
    main()
