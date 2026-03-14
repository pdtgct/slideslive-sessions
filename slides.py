"""
slides.py — Download slide JPEGs and sync XML for a SlidesLive presentation.

Extracts the SlidesLive presentation ID from a neurips.cc session page,
then uses myslideslive (or direct CDN fallback) to enumerate and download
all slide images, plus the slide-to-timecode sync XML.
"""

import re
from pathlib import Path

import httpx

# SlidesLive CDN patterns
SLIDES_CDN_BASE = "https://d3h9ln6psucegz.cloudfront.net"
SYNC_XML_URL = "{cdn}/{presentation_id}/slides/slides.xml"
SLIDE_URL = "{cdn}/{presentation_id}/slides/thumbnails/slide_{n:04d}.jpg"

# Regex patterns to extract SlidesLive presentation ID from neurips.cc page HTML
PRESENTATION_ID_PATTERNS = [
    r'slideslive\.com/embed/presentation/(\d+)',
    r'slideslive-(\d+)',
    r'"presentation_id"\s*:\s*"(\d+)"',
    r'embed\.slideslive\.com/([^"\'&?/]+)',
    r'data-id=["\'](\d+)["\']',
]


def extract_presentation_id(html: str) -> str | None:
    """Extract SlidesLive presentation ID from page HTML."""
    for pattern in PRESENTATION_ID_PATTERNS:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def extract_presentation_id_via_ytdlp(session_url: str, cookies: list[dict]) -> str | None:
    """
    Use yt-dlp's generic extractor to find the SlidesLive embed URL and parse the ID.
    This handles JS-rendered pages where the embed is injected after page load.
    """
    import yt_dlp  # type: ignore

    # Write a temporary netscape cookies file for yt-dlp
    import tempfile
    from auth import cookies_as_netscape

    cookiefile = None
    tmp = None
    if cookies:
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w")
        tmp.close()
        from pathlib import Path as _Path
        cookies_as_netscape(cookies, _Path(tmp.name))
        cookiefile = tmp.name

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(session_url, download=False)
        if info is None:
            return None
        # info may be a playlist; check entries too
        entries = info.get("entries") or [info]
        for entry in entries:
            if entry is None:
                continue
            # Check extractor name or webpage_url for SlidesLive
            extractor = (entry.get("extractor") or "").lower()
            webpage_url = entry.get("webpage_url") or entry.get("url") or ""
            if "slideslive" in extractor or "slideslive" in webpage_url:
                # Try to extract numeric ID from URL
                m = re.search(r'slideslive\.com/(?:embed/presentation/)?(\d+)', webpage_url)
                if m:
                    return m.group(1)
                # Fall back to yt-dlp's own 'id' field
                entry_id = entry.get("id", "")
                if re.fullmatch(r'\d+', entry_id):
                    return entry_id
        return None
    except Exception:
        return None
    finally:
        if tmp:
            import os
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


def extract_page_info(html: str) -> dict:
    """Extract title and abstract from a NeurIPS session page."""
    from html import unescape

    title = ""
    abstract = ""

    # Title: <h1> or <title>
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if m:
        title = unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
    if not title:
        m = re.search(r'<title>(.*?)</title>', html, re.S)
        if m:
            title = unescape(m.group(1)).strip()

    # Abstract: NeurIPS uses a <div> or <p> with class containing "abstract"
    m = re.search(r'class="[^"]*abstract[^"]*"[^>]*>(.*?)</(?:div|p|section)>', html, re.S)
    if m:
        abstract = unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()

    return {"title": title, "abstract": abstract}


def fetch_session_page(url: str, cookies: list[dict]) -> str:
    """Fetch session page HTML using saved auth cookies."""
    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    headers = {
        "Cookie": cookie_header,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


def download_sync_xml(presentation_id: str, output_dir: Path) -> Path | None:
    """Download the slide timing sync XML file."""
    xml_url = SYNC_XML_URL.format(cdn=SLIDES_CDN_BASE, presentation_id=presentation_id)
    xml_path = output_dir / "sync.xml"

    if xml_path.exists():
        print(f"  sync.xml already exists, skipping.")
        return xml_path

    with httpx.Client(timeout=30) as client:
        try:
            response = client.get(xml_url)
            response.raise_for_status()
            xml_path.write_bytes(response.content)
            print(f"  Downloaded sync.xml ({len(response.content)} bytes)")
            return xml_path
        except httpx.HTTPStatusError as e:
            print(f"  Warning: Could not download sync.xml ({e.response.status_code})")
            return None


def download_slides_myslideslive(presentation_id: str, slides_dir: Path) -> int:
    """Download slides using the myslideslive library."""
    try:
        from myslideslive import SlidesLive  # type: ignore

        slides_dir.mkdir(parents=True, exist_ok=True)
        sl = SlidesLive(f"https://slideslive.com/{presentation_id}")
        slide_count = sl.download_slides(str(slides_dir))
        return slide_count
    except ImportError:
        print("  myslideslive not available, falling back to CDN download.")
        return 0
    except Exception as e:
        print(f"  myslideslive failed ({e}), falling back to CDN download.")
        return 0


def download_slides_cdn(presentation_id: str, slides_dir: Path) -> int:
    """Download slides directly from CloudFront CDN (fallback)."""
    slides_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    with httpx.Client(timeout=30) as client:
        n = 1
        while True:
            slide_url = SLIDE_URL.format(
                cdn=SLIDES_CDN_BASE, presentation_id=presentation_id, n=n
            )
            dest = slides_dir / f"{n:03d}.jpg"

            if dest.exists():
                downloaded += 1
                n += 1
                continue

            try:
                response = client.get(slide_url)
                if response.status_code == 404:
                    break
                response.raise_for_status()
                dest.write_bytes(response.content)
                downloaded += 1
                print(f"  Slide {n:03d}.jpg ({len(response.content) // 1024}KB)", end="\r")
                n += 1
            except httpx.HTTPStatusError:
                break

    if downloaded:
        print(f"  Downloaded {downloaded} slides via CDN.")
    return downloaded


def download(
    session_url: str,
    output_dir: Path,
    cookies: list[dict],
    presentation_id: str | None = None,
) -> dict:
    """
    Main entry point: fetch session page, extract presentation ID,
    download slides and sync XML.

    Returns metadata dict with: presentation_id, slide_count.
    """
    slides_dir = output_dir / "slides"

    # Extract presentation ID if not provided
    page_info: dict = {}
    if not presentation_id:
        print(f"Fetching session page: {session_url}")
        html = fetch_session_page(session_url, cookies)
        page_info = extract_page_info(html)
        presentation_id = extract_presentation_id(html)
        if not presentation_id:
            print("  Static HTML regex found nothing — trying yt-dlp extractor...")
            presentation_id = extract_presentation_id_via_ytdlp(session_url, cookies)
        if not presentation_id:
            print("  Warning: Could not find SlidesLive presentation ID.")
            print("  Slides will be skipped. Re-run with --presentation-id <id> to download them.")
            return {"presentation_id": None, "slide_count": 0, **page_info}

    print(f"Presentation ID: {presentation_id}")

    # Download sync XML
    download_sync_xml(presentation_id, output_dir)

    # Download slides
    existing_slides = list(slides_dir.glob("*.jpg")) if slides_dir.exists() else []
    if existing_slides:
        slide_count = len(existing_slides)
        print(f"  {slide_count} slides already downloaded, skipping.")
    else:
        slide_count = download_slides_myslideslive(presentation_id, slides_dir)
        if not slide_count:
            slide_count = download_slides_cdn(presentation_id, slides_dir)

    return {
        "presentation_id": presentation_id,
        "slide_count": slide_count,
        **page_info,
    }
