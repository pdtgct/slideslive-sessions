"""
capture.py — Main CLI orchestrator for NeurIPS session capture.

Usage:
    python capture.py <neurips-session-url> [<url2> ...]
    python capture.py --help

For each URL, runs the full pipeline:
  1. Download slides (JPEG) + sync XML
  2. Download video (MP4) via yt-dlp
  3. Extract audio (MP3) + transcribe (Whisper)
  4. Generate structured notes (Claude)

Steps are skipped if output files already exist (idempotent re-runs).
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def url_to_slug(url: str) -> str:
    """Convert a neurips.cc session URL to a filesystem-safe directory name."""
    # e.g. https://neurips.cc/virtual/2025/poster/12345 → neurips-2025-poster-12345
    url = url.rstrip("/")
    match = re.search(r'neurips\.cc/virtual/(\d+)/([^/]+)/(\d+)', url)
    if match:
        year, kind, session_id = match.groups()
        return f"neurips-{year}-{kind}-{session_id}"
    # Fallback: sanitize the URL path
    path = re.sub(r'https?://[^/]+', '', url)
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', path).strip('-')
    return slug or "session"


# ---------------------------------------------------------------------------
# Video download
# ---------------------------------------------------------------------------

def download_video(session_url: str, output_dir: Path, cookies_path: Path) -> bool:
    """Download session video using yt-dlp. Returns True if video is available."""
    import yt_dlp  # type: ignore

    if not shutil.which("ffmpeg"):
        print("  ERROR: ffmpeg not found on PATH.")
        print("    macOS:  brew install ffmpeg")
        print("    Ubuntu: sudo apt install ffmpeg")
        print("  Video download requires ffmpeg. Skipping video step.")
        return False

    video_path = output_dir / "video.mp4"
    if video_path.exists():
        print(f"  video.mp4 already exists, skipping download.")
        return True

    netscape_cookies = output_dir / ".cookies.txt"
    if cookies_path.exists():
        from auth import load_cookies, cookies_as_netscape
        cookies = load_cookies(cookies_path)
        cookies_as_netscape(cookies, netscape_cookies)
        cookiefile = str(netscape_cookies)
    else:
        cookiefile = None

    ydl_opts = {
        "outtmpl": str(output_dir / "video.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
    }
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    print(f"Downloading video from {session_url} ...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(session_url, download=True)
            if result is None:
                print("  yt-dlp returned no result — video may not be available.")
                return False
        # Rename to video.mp4 if needed
        for ext in ("mp4", "mkv", "webm"):
            candidate = output_dir / f"video.{ext}"
            if candidate.exists() and candidate != video_path:
                candidate.rename(video_path)
                break
        return video_path.exists()
    except yt_dlp.utils.DownloadError as e:
        print(f"  yt-dlp download error: {e}")
        return False
    finally:
        if netscape_cookies.exists():
            netscape_cookies.unlink()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def write_metadata(output_dir: Path, url: str, slug: str, slides_meta: dict) -> None:
    """Write metadata.json and page.md for the session."""
    metadata_path = output_dir / "metadata.json"
    if metadata_path.exists():
        # Merge with existing
        existing = json.loads(metadata_path.read_text())
        existing.update(slides_meta)
        existing.setdefault("url", url)
        existing.setdefault("slug", slug)
        metadata_path.write_text(json.dumps(existing, indent=2))
        metadata = existing
    else:
        metadata = {
            "url": url,
            "slug": slug,
            "title": slug,
            **slides_meta,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2))
    print(f"  metadata.json written.")

    page_md_path = output_dir / "page.md"
    if not page_md_path.exists():
        title = metadata.get("title") or slug
        abstract = metadata.get("abstract", "")
        lines = [f"# {title}", "", f"**URL:** {url}", ""]
        if abstract:
            lines += ["## Abstract", "", abstract, ""]
        page_md_path.write_text("\n".join(lines))
        print(f"  page.md written.")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def capture_session(
    url: str,
    output_root: Path,
    cookies_path: Path,
    presentation_id: str | None = None,
    whisper_model: str | None = None,
    skip_video: bool = False,
    skip_notes: bool = False,
    recreate_notes: bool = False,
    clean_media: bool = False,
) -> None:
    slug = url_to_slug(url)
    output_dir = output_root / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"Session: {slug}")
    print(f"Output:  {output_dir}")
    print(f"{'='*60}")

    # Step 1: Load cookies
    cookies = []
    if cookies_path.exists():
        from auth import load_cookies
        cookies = load_cookies(cookies_path)
    else:
        print(
            f"Warning: No cookies file found at {cookies_path}. "
            "Some content may be inaccessible. Run `python auth.py` to log in."
        )

    # Step 2: Download slides + metadata
    print("\n[1/4] Downloading slides...")
    import slides as slides_module
    slides_meta = slides_module.download(
        session_url=url,
        output_dir=output_dir,
        cookies=cookies,
        presentation_id=presentation_id,
    )
    write_metadata(output_dir, url, slug, slides_meta)

    # Step 3: Download video
    if not skip_video:
        print("\n[2/4] Downloading video...")
        has_video = download_video(url, output_dir, cookies_path)
        if not has_video:
            print("  No video available — skipping audio/transcription.")
            skip_notes_due_to_no_video = True
        else:
            skip_notes_due_to_no_video = False
    else:
        print("\n[2/4] Video download skipped (--no-video).")
        skip_notes_due_to_no_video = False

    # Step 4: Transcribe
    video_path = output_dir / "video.mp4"
    if video_path.exists():
        print("\n[3/4] Transcribing audio...")
        import transcribe as transcribe_module
        transcribe_module.run(output_dir, model_name=whisper_model)
    else:
        print("\n[3/4] No video.mp4 found — skipping transcription.")

    # Step 5: Generate notes
    transcript_path = output_dir / "transcript.txt"
    if not skip_notes and transcript_path.exists():
        print("\n[4/4] Generating notes...")
        import summarize as summarize_module
        summarize_module.generate_notes(output_dir, force=recreate_notes)
    elif skip_notes:
        print("\n[4/4] Notes generation skipped (--no-notes).")
    else:
        print("\n[4/4] No transcript.txt — skipping notes generation.")

    # Clean media if requested
    if clean_media:
        for fname in ("video.mp4", "audio.mp3"):
            fpath = output_dir / fname
            if fpath.exists():
                fpath.unlink()
                print(f"  Removed {fname}.")

    print(f"\nDone! Output in: {output_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Capture slides, video, and notes from NeurIPS sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python capture.py https://neurips.cc/virtual/2025/poster/12345
  python capture.py --no-video https://neurips.cc/virtual/2025/poster/12345
  python capture.py --cookies my_cookies.json <url1> <url2>

First run:
  python auth.py        # log in to neurips.cc, saves cookies.json
  python capture.py <url>
""",
    )
    parser.add_argument("urls", nargs="+", help="neurips.cc session URLs")
    parser.add_argument(
        "--cookies",
        default="cookies.json",
        help="Path to saved browser cookies (default: cookies.json)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Root output directory (default: $OUTPUT_DIR or ./output)",
    )
    parser.add_argument(
        "--whisper-model",
        default=None,
        help="Whisper model size (default: $WHISPER_MODEL or 'small')",
    )
    parser.add_argument(
        "--presentation-id",
        default=None,
        help="SlidesLive presentation ID (if auto-detection fails)",
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Skip video download (slides + notes only)",
    )
    parser.add_argument(
        "--no-notes",
        action="store_true",
        help="Skip notes generation",
    )
    parser.add_argument(
        "--recreate-notes",
        action="store_true",
        help="Regenerate notes.md even if it already exists",
    )
    parser.add_argument(
        "--clean-media",
        action="store_true",
        help="Delete video.mp4 and audio.mp3 after successful capture",
    )

    args = parser.parse_args()

    output_root = Path(args.output_dir or os.environ.get("OUTPUT_DIR", "./output"))
    cookies_path = Path(args.cookies)

    if not cookies_path.exists():
        print(f"Note: No cookies file at {cookies_path}.")
        print("Run `python auth.py` first if the session requires login.")

    for url in args.urls:
        try:
            capture_session(
                url=url,
                output_root=output_root,
                cookies_path=cookies_path,
                presentation_id=args.presentation_id,
                whisper_model=args.whisper_model,
                skip_video=args.no_video,
                skip_notes=args.no_notes,
                recreate_notes=args.recreate_notes,
                clean_media=args.clean_media,
            )
        except KeyboardInterrupt:
            print("\nInterrupted.")
            sys.exit(1)
        except Exception as e:
            print(f"\nERROR processing {url}: {e}")
            import traceback
            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()
