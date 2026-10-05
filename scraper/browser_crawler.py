
from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser

import requests
import trafilatura
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from pypdf import PdfReader


TRACKING = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid"
}


def canonicalize(url: str) -> str:
    p = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k.lower() not in TRACKING]
    query.sort()
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((p.scheme.lower() or "https", p.netloc.lower(), path, "", urlencode(query), ""))


def slug(value: str, limit: int = 130) -> str:
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    if len(value) > limit:
        h = hashlib.sha1(value.encode()).hexdigest()[:10]
        value = value[:limit-11] + "_" + h
    return value or "page"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


class RelevantBrowserCrawler:
    def __init__(self, config_path="config.json"):
        self.cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.out = Path(self.cfg["output_dir"])
        self.pages = self.out / "pages"
        self.pdfs = self.out / "pdfs"
        self.state = self.out / "state"
        self.html_dir = self.out / "html"
        for d in [self.pages, self.pdfs, self.state]:
            d.mkdir(parents=True, exist_ok=True)
        if self.cfg.get("save_html"):
            self.html_dir.mkdir(parents=True, exist_ok=True)

        self.visited_path = self.state / "visited.jsonl"
        self.queue_path = self.state / "queue.json"
        self.manifest_path = self.out / "manifest.csv"
        self.errors_path = self.out / "errors.jsonl"
        self.discovery_path = self.out / "discovered_links.jsonl"

        self.visited = self._read_visited()
        self.content_hashes = self._read_hashes()
        self.robots = {}
        self.http = requests.Session()
        self.http.headers.update({
            "User-Agent": "BRACU-KB-Educational-Crawler/2.0"
        })

    def _read_visited(self):
        s = set()
        if self.visited_path.exists():
            for line in self.visited_path.read_text(encoding="utf-8").splitlines():
                try:
                    s.add(json.loads(line)["url"])
                except Exception:
                    pass
        return s

    def _read_hashes(self):
        s = set()
        if self.manifest_path.exists():
            with self.manifest_path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("content_sha256"):
                        s.add(row["content_sha256"])
        return s

    def _save_queue(self, q):
        self.queue_path.write_text(json.dumps(list(q), indent=2), encoding="utf-8")

    def _load_queue(self):
        if self.queue_path.exists():
            try:
                return deque(json.loads(self.queue_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return deque(self.cfg["start_urls"])

    def allowed_domain(self, url):
        return urlparse(url).netloc.lower() in {x.lower() for x in self.cfg["allowed_domains"]}

    def classify(self, text, url):
        haystack = (text + " " + url).lower()
        scores = {}
        for cat, kws in self.cfg["categories"].items():
            scores[cat] = sum(1 for kw in kws if kw.lower() in haystack)
        best = max(scores, key=scores.get)
        return best, scores[best]

    def relevant(self, text, url):
        _, score = self.classify(text, url)
        # Seed/home/navigation pages are allowed so they can lead us to relevant content.
        path = urlparse(url).path.strip("/")
        return score > 0 or len(path.split("/")) <= 1

    def _robot(self, url):
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            rp = RobotFileParser()
            robots_url = origin + "/robots.txt"
            rp.set_url(robots_url)
            try:
                r = self.http.get(robots_url, timeout=15)
                if r.ok:
                    rp.parse(r.text.splitlines())
                else:
                    rp.parse([])
            except Exception:
                rp.parse([])
            self.robots[origin] = rp
        return self.robots[origin]

    def can_fetch(self, url):
        try:
            return self._robot(url).can_fetch("BRACU-KB-Educational-Crawler/2.0", url)
        except Exception:
            return True

    def log_error(self, url, error):
        with self.errors_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "url": url, "error": str(error),
                "time": datetime.now(timezone.utc).isoformat()
            }, ensure_ascii=False) + "\n")

    def mark_visited(self, url, status):
        with self.visited_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "url": url, "status": status,
                "time": datetime.now(timezone.utc).isoformat()
            }, ensure_ascii=False) + "\n")
        self.visited.add(url)

    def append_manifest(self, row):
        fields = [
            "url", "title", "category", "relevance_score", "source_type",
            "status", "local_file", "content_sha256", "fetched_at"
        ]
        exists = self.manifest_path.exists()
        with self.manifest_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if not exists:
                w.writeheader()
            w.writerow(row)

    def discover_log(self, from_url, to_url, label, category, score):
        with self.discovery_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "from_url": from_url,
                "to_url": to_url,
                "label": label,
                "category": category,
                "relevance_score": score
            }, ensure_ascii=False) + "\n")

    async def safe_expand_controls(self, page):
        clicked = 0
        max_clicks = self.cfg["max_clicks_per_page"]
        safe_phrases = [x.lower() for x in self.cfg["safe_click_text"]]

        # 1) ARIA / Bootstrap-style expandable controls
        candidates = page.locator(
            'button[aria-expanded="false"], '
            '[role="button"][aria-expanded="false"], '
            'button[data-bs-toggle="collapse"], '
            'button[data-toggle="collapse"], '
            'a[data-bs-toggle="collapse"], '
            'a[data-toggle="collapse"], '
            '[role="tab"]'
        )

        count = min(await candidates.count(), max_clicks)
        for i in range(count):
            el = candidates.nth(i)
            try:
                if await el.is_visible():
                    await el.click(timeout=1500)
                    clicked += 1
                    await page.wait_for_timeout(self.cfg["post_click_wait_ms"])
            except Exception:
                pass
            if clicked >= max_clicks:
                return clicked

        # 2) Content-oriented visible-text buttons/links.
        # Avoid action/transaction controls.
        all_controls = page.locator('button, [role="button"], a')
        count = min(await all_controls.count(), 500)
        forbidden = (
            "apply now", "submit", "login", "log in", "sign in", "pay",
            "payment", "register now", "delete", "remove", "logout",
            "sign up", "enroll", "checkout", "send"
        )

        for i in range(count):
            if clicked >= max_clicks:
                break
            el = all_controls.nth(i)
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.inner_text()).strip().lower()
                if not txt:
                    continue
                if any(x in txt for x in forbidden):
                    continue
                if any(p in txt for p in safe_phrases):
                    href = await el.get_attribute("href")
                    # Follow normal links through the crawl queue instead of clicking navigation.
                    if href:
                        continue
                    await el.click(timeout=1500)
                    clicked += 1
                    await page.wait_for_timeout(self.cfg["post_click_wait_ms"])
            except Exception:
                pass

        return clicked

    async def collect_internal_links(self, page, current_url):
        links = {}
        locator = page.locator("a[href]")
        count = await locator.count()

        for i in range(min(count, 3000)):
            a = locator.nth(i)
            try:
                href = await a.get_attribute("href")
                if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                    continue
                label = (await a.inner_text()).strip()
                full = canonicalize(urljoin(current_url, href))
                if not full.startswith(("http://", "https://")):
                    continue
                if not self.allowed_domain(full):
                    continue
                category, score = self.classify(label, full)
                if self.relevant(label, full):
                    links[full] = (label[:300], category, score)
            except Exception:
                pass

        return links

    def clean_content(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else url

        text = trafilatura.extract(
            html,
            url=url,
            include_links=True,
            include_tables=True,
            include_comments=False,
            favor_recall=True
        )

        if not text or len(text.strip()) < 100:
            for tag in soup(["script", "style", "noscript", "svg", "form"]):
                tag.decompose()
            main = soup.find("main") or soup.find("article") or soup.body or soup
            text = html_to_md(str(main), heading_style="ATX").strip()

        return title, text.strip()

    def save_markdown(self, url, title, body, category, score):
        digest = sha(body)
        if digest in self.content_hashes:
            return "", digest

        host = urlparse(url).netloc.replace(".", "_")
        name = host + "__" + slug(urlparse(url).path.strip("/") or "home") + ".md"
        path = self.pages / name

        fm = (
            "---\n"
            f"title: {json.dumps(title, ensure_ascii=False)}\n"
            f"source_url: {json.dumps(url, ensure_ascii=False)}\n"
            f"category: {json.dumps(category)}\n"
            f"relevance_score: {score}\n"
            f"fetched_at: {json.dumps(datetime.now(timezone.utc).isoformat())}\n"
            f"content_sha256: {json.dumps(digest)}\n"
            'source_type: "webpage"\n'
            "---\n\n"
        )
        path.write_text(fm + "# " + title + "\n\n" + body + "\n", encoding="utf-8")
        self.content_hashes.add(digest)
        return str(path), digest

    def fetch_pdf(self, url, category, score):
        r = self.http.get(url, timeout=30)
        r.raise_for_status()
        name = slug(urlparse(url).path.strip("/") or "document")
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        pdf = self.pdfs / name
        pdf.write_bytes(r.content)

        text_parts = []
        try:
            reader = PdfReader(str(pdf))
            for i, p in enumerate(reader.pages, 1):
                text_parts.append(f"## Page {i}\n\n{(p.extract_text() or '').strip()}")
        except Exception as e:
            self.log_error(url, f"PDF parse failed: {e}")

        body = "\n\n".join(text_parts).strip()
        digest = sha(body if body else r.content.hex())
        local = str(pdf)

        if body and digest not in self.content_hashes:
            md_path = self.pages / (Path(name).stem + ".md")
            fm = (
                "---\n"
                f"title: {json.dumps(Path(name).stem, ensure_ascii=False)}\n"
                f"source_url: {json.dumps(url, ensure_ascii=False)}\n"
                f"category: {json.dumps(category)}\n"
                f"relevance_score: {score}\n"
                f"fetched_at: {json.dumps(datetime.now(timezone.utc).isoformat())}\n"
                f"content_sha256: {json.dumps(digest)}\n"
                'source_type: "pdf"\n'
                "---\n\n"
            )
            md_path.write_text(fm + body + "\n", encoding="utf-8")
            local = str(md_path)
            self.content_hashes.add(digest)

        self.append_manifest({
            "url": url,
            "title": Path(name).stem,
            "category": category,
            "relevance_score": score,
            "source_type": "pdf",
            "status": r.status_code,
            "local_file": local,
            "content_sha256": digest,
            "fetched_at": datetime.now(timezone.utc).isoformat()
        })

    async def crawl(self):
        q = self._load_queue()
        processed = 0
        max_pages = int(self.cfg["max_pages"])

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="BRACU-KB-Educational-Crawler/2.0",
                accept_downloads=False,
                java_script_enabled=True
            )
            page = await context.new_page()
            page.set_default_navigation_timeout(self.cfg["navigation_timeout_ms"])

            print(f"Queued: {len(q)} | already visited: {len(self.visited)}")

            while q and processed < max_pages:
                url = canonicalize(q.popleft())
                if url in self.visited or not self.allowed_domain(url):
                    continue

                category, base_score = self.classify("", url)

                if not self.can_fetch(url):
                    print("[ROBOTS SKIP]", url)
                    self.mark_visited(url, "robots_disallowed")
                    continue

                if url.lower().endswith(".pdf"):
                    try:
                        self.fetch_pdf(url, category, base_score)
                        self.mark_visited(url, "pdf")
                    except Exception as e:
                        self.log_error(url, e)
                        self.mark_visited(url, "error")
                    processed += 1
                    self._save_queue(q)
                    continue

                print(f"[{category}:{base_score}] {url}")

                try:
                    response = await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(700)

                    final_url = canonicalize(page.url)
                    if not self.allowed_domain(final_url):
                        self.mark_visited(url, "redirect_outside")
                        continue

                    # Expand page-local content before extraction.
                    clicks = await self.safe_expand_controls(page)

                    # Scroll to trigger lazy-loaded content.
                    for _ in range(4):
                        await page.mouse.wheel(0, 1800)
                        await page.wait_for_timeout(250)

                    html = await page.content()
                    if self.cfg.get("save_html"):
                        (self.html_dir / (slug(final_url) + ".html")).write_text(
                            html, encoding="utf-8", errors="ignore"
                        )

                    title, body = self.clean_content(html, final_url)
                    category, score = self.classify(title + " " + body[:5000], final_url)

                    local, digest = "", ""
                    if score > 0 or final_url in map(canonicalize, self.cfg["start_urls"]):
                        local, digest = self.save_markdown(
                            final_url, title, body, category, score
                        )

                    links = await self.collect_internal_links(page, final_url)
                    for target, (label, lcat, lscore) in links.items():
                        self.discover_log(final_url, target, label, lcat, lscore)
                        if target not in self.visited:
                            q.append(target)

                    status = response.status if response else "ok"
                    self.append_manifest({
                        "url": final_url,
                        "title": title,
                        "category": category,
                        "relevance_score": score,
                        "source_type": "webpage",
                        "status": status,
                        "local_file": local,
                        "content_sha256": digest,
                        "fetched_at": datetime.now(timezone.utc).isoformat()
                    })

                    self.mark_visited(url, status)
                    print(f"  expanded controls: {clicks} | relevant links found: {len(links)}")
                    processed += 1

                except KeyboardInterrupt:
                    self._save_queue(q)
                    await browser.close()
                    raise
                except PlaywrightTimeoutError as e:
                    self.log_error(url, "navigation timeout")
                    self.mark_visited(url, "timeout")
                    processed += 1
                except Exception as e:
                    self.log_error(url, e)
                    self.mark_visited(url, "error")
                    processed += 1

                self._save_queue(q)
                await asyncio.sleep(float(self.cfg["request_delay_seconds"]))

            await browser.close()
            self._save_queue(q)

        print("Done.")
        print("Processed this run:", processed)
        print("Visited total:", len(self.visited))
        print("Remaining queue:", len(q))
