"""
slides.py — Download slide images and sync XML for a SlidesLive presentation.

Extracts the SlidesLive presentation ID from a neurips.cc session page,
fetches the player's slides_video_service_data API to get the actual slide
URLs (hashed filenames on slideslive-slides.b-cdn.net), then downloads them.
Falls back to myslideslive or legacy CDN enumeration if the API fails.
"""

import re
from pathlib import Path

import httpx

# Legacy CDN (used as last-resort fallback only — most presentations 403 now)
_LEGACY_CDN_BASE = "https://d3h9ln6psucegz.cloudfront.net"
_LEGACY_SYNC_XML_URL = "{cdn}/{presentation_id}/slides/slides.xml"
_LEGACY_SLIDE_URL = "{cdn}/{presentation_id}/slides/thumbnails/slide_{n:04d}.jpg"

# SlidesLive embed base
SLIDESLIVE_EMBED_URL = "https://slideslive.com/embed/presentation/{presentation_id}"

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


def fetch_embed_html(presentation_id: str, session_url: str, cookies: list[dict]) -> str:
    """
    Fetch the SlidesLive embed page HTML.

    This page contains data-player-token and data-slides-video-service-data-url
    as server-rendered attributes on the player div.
    """
    embed_url = SLIDESLIVE_EMBED_URL.format(presentation_id=presentation_id)
    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    headers = {
        "Referer": session_url,
        "Origin": "https://neurips.cc",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        response = client.get(embed_url, headers=headers)
        response.raise_for_status()
        return response.text


def extract_player_data(html: str) -> dict:
    """Extract player token and service data URL from SlidesLive player HTML."""
    token_match = re.search(r'data-player-token="([^"]+)"', html)
    url_match = re.search(r'data-slides-video-service-data-url="([^"]+)"', html)
    return {
        "player_token": token_match.group(1) if token_match else None,
        "service_data_url": url_match.group(1) if url_match else None,
    }


def fetch_slides_service_data(service_data_url: str, player_token: str) -> dict | None:
    """
    Fetch the slide list from the SlidesLive slides_video_service_data endpoint.

    Returns the parsed JSON dict, or None on failure.
    """
    headers = {
        "Authorization": f"Bearer {player_token}",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    with httpx.Client(timeout=30) as client:
        try:
            response = client.get(service_data_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"  Could not fetch service data: {e}")
            return None


def download_slides_from_service_data(service_data: dict, slides_dir: Path) -> int:
    """
    Download slides whose URLs are listed in the service data JSON.

    SlidesLive returns URLs like:
      https://slideslive-slides.b-cdn.net/{id}/slides/original/{hash}.png
    The JSON structure may vary; we try several known key shapes.
    """
    # Normalise: collect a flat list of URL strings
    raw: list = []
    for key in ("slides", "slide_urls", "images"):
        val = service_data.get(key)
        if isinstance(val, list) and val:
            raw = val
            break

    if not raw:
        print(f"  service data keys: {list(service_data.keys())} — no slide list found")
        return 0

    slides_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for i, item in enumerate(raw, 1):
            if isinstance(item, str):
                url = item
            elif isinstance(item, dict):
                url = item.get("url") or item.get("image") or item.get("src") or ""
            else:
                continue

            if not url:
                continue

            # Keep the original extension (usually .png)
            ext = url.split("?")[0].rsplit(".", 1)[-1] if "." in url.split("?")[0] else "png"
            dest = slides_dir / f"{i:03d}.{ext}"

            if dest.exists():
                downloaded += 1
                continue

            try:
                response = client.get(url)
                response.raise_for_status()
                dest.write_bytes(response.content)
                downloaded += 1
                print(f"  Slide {i:03d} ({len(response.content) // 1024}KB)    ", end="\r")
            except httpx.HTTPStatusError as e:
                print(f"\n  Warning: slide {i} failed ({e.response.status_code}): {url}")

    if downloaded:
        print(f"  Downloaded {downloaded} slides via service data.          ")
    return downloaded


def download_slides_playwright(
    session_url: str,
    slides_dir: Path,
    cookies: list[dict],
) -> int:
    """
    Use a headless browser to click through all slides in the SlidesLive player
    embedded in the NeurIPS session page, collect each slide's image URL, then
    download them and write slides/slides.pdf.

    Returns the number of slides downloaded.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("  Launching headless browser to collect slide URLs...")

    slide_urls: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        # Load saved cookies
        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()
        page.goto(session_url, wait_until="load", timeout=60_000)

        # SlidesLive player is in an iframe on the NeurIPS page
        iframe_sel = "iframe[src*='slideslive.com']"
        try:
            page.wait_for_selector(iframe_sel, timeout=20_000)
        except PWTimeout:
            print("  Timed out waiting for SlidesLive iframe.")
            browser.close()
            return 0

        # Get the frame object
        iframe_element = page.query_selector(iframe_sel)
        frame = iframe_element.content_frame()
        if frame is None:
            print("  Could not access iframe content.")
            browser.close()
            return 0

        slide_img_sel = "[data-slp-target='slidesElement'] img"
        player_root_sel = "[data-slp-target='rootElement']"

        # Wait for the player to finish loading (slp--liveStarted appears when ready).
        # If it takes too long, click the player to nudge initialization.
        for attempt in range(3):
            try:
                frame.wait_for_function(
                    "() => document.querySelector('[data-slp-target=\"rootElement\"]')"
                    "       ?.classList.contains('slp--liveStarted') ?? false",
                    timeout=20_000,
                )
                break  # player is ready
            except PWTimeout:
                if attempt == 0:
                    # Nudge: click center of the player
                    try:
                        frame.locator(player_root_sel).click(timeout=3_000)
                    except Exception:
                        pass
                elif attempt == 1:
                    # Nudge: try the play button
                    try:
                        frame.locator("[data-slp-target='play']").click(timeout=3_000)
                    except Exception:
                        pass
        else:
            print("  Warning: player did not reach liveStarted state; trying anyway...")

        # Wait for the first slide image to appear inside the iframe
        try:
            frame.wait_for_selector(slide_img_sel, timeout=30_000)
        except PWTimeout:
            print("  Timed out waiting for first slide image in iframe.")
            browser.close()
            return 0

        # Read total slide count
        try:
            count_text = frame.inner_text("[data-slp-target='slideCount']")
            total = int(count_text.strip())
        except Exception:
            total = None
        print(f"  Player reports {total} slides." if total else "  Could not read slide count.")

        # Click through all slides via keyboard shortcut (Shift+→)
        # Initial focus
        frame.locator(player_root_sel).focus()

        # Read slide count now that the player is active
        if total is None:
            try:
                count_text = frame.inner_text("[data-slp-target='slideCount']")
                total = int(count_text.strip())
                print(f"  Player reports {total} slides.")
            except Exception:
                pass

        seen: set[str] = set()

        for i in range(total or 500):
            # Get current slide src
            try:
                src = frame.get_attribute(slide_img_sel, "src") or ""
            except Exception:
                break

            # Strip query params for dedup, but keep full URL for download
            src_clean = src.split("?")[0]
            if src_clean and src_clean not in seen:
                seen.add(src_clean)
                slide_urls.append(src)

            print(f"  Collecting slide {i + 1}/{total or '?'}    ", end="\r")

            # Stop if we've reached the total
            if total and len(seen) >= total:
                break

            # Shift+→ is the SlidesLive keyboard shortcut for next slide
            page.keyboard.press("Shift+ArrowRight")

            # Wait for slide to advance: src changes OR img disappears (video slide)
            try:
                frame.wait_for_function(
                    """([sel, prev]) => {
                        const img = document.querySelector(sel);
                        return !img || img.src !== prev;
                    }""",
                    arg=[slide_img_sel, src],
                    timeout=5_000,
                )
            except PWTimeout:
                # Neither happened — we're at the last slide
                break

            # If img disappeared (video-type slide), keep pressing → to skip past it
            for _ in range(50):
                if frame.evaluate(f"document.querySelector(\"{slide_img_sel}\") !== null"):
                    break  # img reappeared — back to an image slide
                page.keyboard.press("Shift+ArrowRight")
                page.wait_for_timeout(200)
            else:
                # Couldn't get back to an image slide — end of navigable content
                break

        browser.close()

    print(f"\n  Collected {len(slide_urls)} unique slide URLs.")

    if not slide_urls:
        return 0

    # Download images
    slides_dir.mkdir(parents=True, exist_ok=True)
    downloaded_paths: list[Path] = []

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for i, url in enumerate(slide_urls, 1):
            ext = url.split("?")[0].rsplit(".", 1)[-1] if "." in url.split("?")[0] else "png"
            dest = slides_dir / f"{i:03d}.{ext}"
            if dest.exists():
                downloaded_paths.append(dest)
                continue
            try:
                response = client.get(url)
                response.raise_for_status()
                dest.write_bytes(response.content)
                downloaded_paths.append(dest)
                print(f"  Downloading slide {i}/{len(slide_urls)}    ", end="\r")
            except httpx.HTTPStatusError as e:
                print(f"\n  Warning: slide {i} failed ({e.response.status_code})")

    print(f"  Downloaded {len(downloaded_paths)} slides.              ")

    # Build PDF
    if downloaded_paths:
        _build_pdf(downloaded_paths, slides_dir)

    return len(downloaded_paths)


def _build_pdf(image_paths: list[Path], slides_dir: Path) -> None:
    """Combine downloaded slide images into a single slides.pdf."""
    try:
        from PIL import Image
    except ImportError:
        print("  Pillow not installed — skipping PDF generation.")
        return

    pdf_path = slides_dir.parent / "slides.pdf"
    if pdf_path.exists():
        print("  slides.pdf already exists, skipping.")
        return

    images = []
    for p in image_paths:
        try:
            img = Image.open(p).convert("RGB")
            images.append(img)
        except Exception as e:
            print(f"  Warning: could not open {p.name}: {e}")

    if not images:
        return

    images[0].save(
        pdf_path,
        save_all=True,
        append_images=images[1:],
    )
    print(f"  slides.pdf written ({len(images)} pages).")


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
    xml_url = _LEGACY_SYNC_XML_URL.format(cdn=_LEGACY_CDN_BASE, presentation_id=presentation_id)
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
    """Download slides from the legacy CloudFront CDN (last-resort fallback)."""
    slides_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    with httpx.Client(timeout=30) as client:
        n = 1
        while True:
            slide_url = _LEGACY_SLIDE_URL.format(
                cdn=_LEGACY_CDN_BASE, presentation_id=presentation_id, n=n
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

    # Download sync XML (best-effort; 403 on newer presentations is normal)
    download_sync_xml(presentation_id, output_dir)

    # Download slides
    existing_slides = (
        list(slides_dir.glob("*.jpg")) + list(slides_dir.glob("*.png"))
        if slides_dir.exists() else []
    )
    if existing_slides:
        slide_count = len(existing_slides)
        print(f"  {slide_count} slides already downloaded, skipping.")
    else:
        slide_count = 0

        # Primary: Playwright — click through the live player to collect slide URLs
        try:
            slide_count = download_slides_playwright(session_url, slides_dir, cookies)
        except Exception as e:
            print(f"  Playwright approach failed: {e}")

        # Fallback 1: myslideslive library
        if not slide_count:
            slide_count = download_slides_myslideslive(presentation_id, slides_dir)

        # Fallback 2: legacy CDN enumeration
        if not slide_count:
            slide_count = download_slides_cdn(presentation_id, slides_dir)

    return {
        "presentation_id": presentation_id,
        "slide_count": slide_count,
        **page_info,
    }
