"""Drive the prototype in a headless browser and capture each panel.

Not part of the deliverable - a development aid for reviewing the UI without
running it locally. Run from the repository root:

    python scripts/screenshot_panels.py [outdir]
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path[:0] = ["src", "."]

import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app.app import app  # noqa: E402

PORT = 8787
BASE = f"http://127.0.0.1:{PORT}"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")


def serve() -> uvicorn.Server:
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(60):
        if server.started:
            return server
        time.sleep(0.25)
    raise RuntimeError("server did not start")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = serve()
    shots: list[str] = []

    with sync_playwright() as p:
        chrome = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        browser = p.chromium.launch(executable_path=chrome)
        page = browser.new_page(viewport={"width": 1420, "height": 1000})
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(1500)

        def shot(name: str) -> None:
            path = OUT / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            shots.append(str(path))

        # 1. Site, as it opens
        shot("01-site")

        # 2. A different sub-region, to show the conditions table reacting
        page.select_option("#site-region", "PL-lagoon")
        page.wait_for_timeout(800)
        shot("02-site-lagoon")

        # Back to Lithuania and commit the site
        page.select_option("#site-region", "LT-coastal")
        page.fill("#site-label", "Melnrage pilot")
        page.wait_for_timeout(400)
        page.click("#site-set_site")
        page.wait_for_timeout(800)

        # 3. Catalogue
        page.click("a:has-text('Catalogue')")
        page.wait_for_timeout(900)
        shot("03-catalogue")

        # 4. Results before Assess - the empty state
        page.click("a:has-text('Results')")
        page.wait_for_timeout(700)
        shot("04-results-empty")

        # 5. Results after Assess
        page.click("#assess")
        page.wait_for_timeout(2500)
        shot("05-results")

        # 6. Report
        page.click("a:has-text('Report')")
        page.wait_for_timeout(1200)
        shot("06-report")

        # 7. The Start door, to show the mode changing the default scale
        page.select_option("#um-mode", "start")
        page.wait_for_timeout(1200)
        page.click("a:has-text('Results')")
        page.wait_for_timeout(700)
        shot("07-stale-invalidated")

        # 8. About modal
        page.click("#about")
        page.wait_for_timeout(900)
        shot("08-about")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

        # 9. Danish site, where sugar kelp is not contraindicated
        page.click("a:has-text('Site')")
        page.wait_for_timeout(500)
        page.select_option("#site-region", "DK-belt")
        page.fill("#site-label", "Great Belt")
        page.wait_for_timeout(300)
        page.click("#site-set_site")
        page.wait_for_timeout(600)
        page.click("#assess")
        page.wait_for_timeout(2500)
        page.click("a:has-text('Results')")
        page.wait_for_timeout(1200)
        shot("09-results-denmark")

        errors = page.evaluate("() => window.__errors__ || []")
        browser.close()

    server.should_exit = True
    print("\n".join(shots))
    if errors:
        print("JS errors:", errors)


if __name__ == "__main__":
    main()
