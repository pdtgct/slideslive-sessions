"""
auth.py — Browser-based login for neurips.cc via Playwright.

Usage:
    slideslive-auth [--cookies cookies.json]

Opens a headed browser window so the user can complete SSO/Google login
manually, then saves the resulting cookies to cookies.json for reuse.
"""

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://neurips.cc/accounts/login"
LOGGED_IN_INDICATOR = "https://neurips.cc/virtual"  # URL prefix after successful login


def login(cookies_path: Path) -> None:
    print(f"Opening browser for neurips.cc login...")
    print("Complete the login in the browser window, then close it (or it will auto-close).")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto(LOGIN_URL)

        # Wait for the user to complete login: detect navigation away from login page
        try:
            page.wait_for_url(
                lambda url: "login" not in url and "neurips.cc" in url,
                timeout=300_000,  # 5 minutes
            )
        except Exception:
            print("Timed out waiting for login. Exiting.")
            browser.close()
            sys.exit(1)

        cookies = context.cookies()
        browser.close()

    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    cookies_path.write_text(json.dumps(cookies, indent=2))
    print(f"Cookies saved to {cookies_path} ({len(cookies)} cookies).")


def load_cookies(cookies_path: Path) -> list[dict]:
    """Return cookies list from saved cookies.json file."""
    if not cookies_path.exists():
        raise FileNotFoundError(
            f"No cookies file found at {cookies_path}. "
            "Run `slideslive-auth` first to log in."
        )
    return json.loads(cookies_path.read_text())


def cookies_as_header(cookies: list[dict]) -> str:
    """Format cookies list into a Cookie: header value string."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def cookies_as_netscape(cookies: list[dict], path: Path) -> None:
    """Write cookies in Netscape format for yt-dlp --cookies flag."""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path_val = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expires_val = c.get("expires", 0) or 0
        expires = int(expires_val) if expires_val > 0 else 0
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path_val}\t{secure}\t{expires}\t{name}\t{value}")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Log in to neurips.cc and save cookies.")
    parser.add_argument(
        "--cookies",
        default="cookies.json",
        help="Path to save cookies (default: cookies.json)",
    )
    args = parser.parse_args()
    login(Path(args.cookies))


if __name__ == "__main__":
    main()
