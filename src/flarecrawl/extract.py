"""HTML content extraction utilities for Flarecrawl.

Provides main-content extraction, tag filtering, image extraction,
structured data parsing (LD+JSON, OpenGraph, Twitter Cards), and
minimal HTML-to-markdown conversion.

Uses BeautifulSoup4 + lxml for robust HTML parsing.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

# ------------------------------------------------------------------
# Main content extraction
# ------------------------------------------------------------------

# Elements to remove when extracting main content
_STRIP_TAGS = {"nav", "footer", "header", "aside", "script", "style", "noscript", "iframe"}

# Selectors to try for main content (in priority order)
_MAIN_SELECTORS = ["main", "article", "[role=main]", "#content", ".content", "#main"]


def extract_main_content(html: str) -> str:
    """Extract main content from HTML, stripping nav/footer/sidebar.

    Tries known main-content selectors. Falls back to <body> with
    nav/footer/header/aside stripped.

    Returns cleaned HTML string.
    """
    soup = BeautifulSoup(html, "lxml")

    # Try each selector in priority order
    for selector in _MAIN_SELECTORS:
        el = soup.select_one(selector)
        if el and len(el.get_text(strip=True)) > 50:
            # Remove unwanted nested elements
            for tag in el.find_all(_STRIP_TAGS):
                tag.decompose()
            return str(el)

    # Fallback: use body with unwanted tags stripped
    body = soup.find("body")
    if not body:
        return html

    for tag in body.find_all(_STRIP_TAGS):
        tag.decompose()
    return str(body)


# ------------------------------------------------------------------
# Tag filtering
# ------------------------------------------------------------------


def filter_tags(html: str, include: list[str] | None = None,
                exclude: list[str] | None = None) -> str:
    """Filter HTML by CSS selectors.

    include: keep only content matching these selectors.
    exclude: remove content matching these selectors.
    Only one of include/exclude should be set.

    Returns filtered HTML string.
    """
    soup = BeautifulSoup(html, "lxml")

    if include:
        parts = []
        for selector in include:
            parts.extend(soup.select(selector))
        # Build new document from matched elements
        result = BeautifulSoup("<div></div>", "lxml")
        container = result.find("div")
        for part in parts:
            container.append(part.extract())  # type: ignore[union-attr]
        return str(container)

    if exclude:
        for selector in exclude:
            for el in soup.select(selector):
                el.decompose()

    body = soup.find("body")
    return str(body) if body else str(soup)


# ------------------------------------------------------------------
# Image extraction
# ------------------------------------------------------------------


def extract_images(html: str, base_url: str) -> list[dict]:
    """Extract image URLs from HTML.

    Finds <img>, <picture><source>, and <meta property="og:image"> tags.
    Returns list of dicts with url, alt, width, height keys.
    """
    soup = BeautifulSoup(html, "lxml")
    images: list[dict] = []
    seen: set[str] = set()

    # <img> tags
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        url = urljoin(base_url, src)
        if url in seen:
            continue
        seen.add(url)
        images.append({
            "url": url,
            "alt": img.get("alt", ""),
            "width": img.get("width"),
            "height": img.get("height"),
        })

    # <picture><source> tags
    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        if not srcset:
            continue
        # Take first URL from srcset
        first_src = srcset.split(",")[0].strip().split()[0]
        url = urljoin(base_url, first_src)
        if url in seen:
            continue
        seen.add(url)
        images.append({
            "url": url,
            "alt": "",
            "width": None,
            "height": None,
        })

    # <meta property="og:image">
    for meta in soup.find_all("meta", attrs={"property": "og:image"}):
        content = meta.get("content")
        if not content:
            continue
        url = urljoin(base_url, content)
        if url in seen:
            continue
        seen.add(url)
        images.append({
            "url": url,
            "alt": "",
            "width": None,
            "height": None,
        })

    return images


# ------------------------------------------------------------------
# Structured data extraction (LD+JSON, OpenGraph, Twitter Cards)
# ------------------------------------------------------------------


def extract_structured_data(html: str) -> dict:
    """Extract structured data from HTML.

    Parses:
    - <script type="application/ld+json"> blocks
    - <meta property="og:*"> tags (OpenGraph)
    - <meta name="twitter:*"> tags (Twitter Cards)

    Returns dict with ld_json, opengraph, twitter_card keys.
    """
    soup = BeautifulSoup(html, "lxml")

    # LD+JSON
    ld_json: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.get_text(strip=True)
        if not text:
            continue
        try:
            data = json.loads(text)
            if isinstance(data, list):
                ld_json.extend(data)
            else:
                ld_json.append(data)
        except json.JSONDecodeError:
            continue  # Skip malformed JSON

    # OpenGraph
    opengraph: dict[str, str] = {}
    for meta in soup.find_all("meta", attrs={"property": re.compile(r"^og:")}):
        prop = meta.get("property", "")
        content = meta.get("content", "")
        if prop and content:
            # Strip "og:" prefix for cleaner keys
            key = prop[3:]
            opengraph[key] = content

    # Twitter Cards
    twitter_card: dict[str, str] = {}
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")}):
        name = meta.get("name", "")
        content = meta.get("content", "")
        if name and content:
            key = name[8:]  # Strip "twitter:" prefix
            twitter_card[key] = content

    return {
        "ld_json": ld_json,
        "opengraph": opengraph,
        "twitter_card": twitter_card,
    }


# ------------------------------------------------------------------
# Minimal HTML to Markdown converter
# ------------------------------------------------------------------


def html_to_markdown(html: str) -> str:
    """Convert HTML to simple markdown.

    Handles headings, paragraphs, links, lists, bold, italic, code.
    No external dependencies — uses BeautifulSoup for parsing.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove scripts and styles
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    lines: list[str] = []
    _walk(soup, lines)

    # Clean up excessive blank lines
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _walk(element, lines: list[str]) -> None:
    """Recursively walk DOM and build markdown lines."""
    if isinstance(element, str):
        # NavigableString
        text = element.strip()
        if text:
            lines.append(text)
        return

    if not isinstance(element, Tag):
        return

    tag = element.name

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = element.get_text(strip=True)
        if text:
            lines.append(f"\n{'#' * level} {text}\n")
        return

    if tag == "p":
        text = _inline_text(element)
        if text:
            lines.append(f"\n{text}\n")
        return

    if tag == "br":
        lines.append("")
        return

    if tag in ("ul", "ol"):
        lines.append("")
        for i, li in enumerate(element.find_all("li", recursive=False)):
            prefix = f"{i + 1}. " if tag == "ol" else "- "
            text = _inline_text(li)
            if text:
                lines.append(f"{prefix}{text}")
        lines.append("")
        return

    if tag == "pre":
        code = element.get_text()
        lines.append(f"\n```\n{code}\n```\n")
        return

    if tag == "blockquote":
        text = element.get_text(strip=True)
        if text:
            lines.append(f"\n> {text}\n")
        return

    if tag == "hr":
        lines.append("\n---\n")
        return

    if tag == "a":
        text = element.get_text(strip=True)
        href = element.get("href", "")
        if text and href:
            lines.append(f"[{text}]({href})")
        elif text:
            lines.append(text)
        return

    if tag == "img":
        alt = element.get("alt", "")
        src = element.get("src", "")
        if src:
            lines.append(f"![{alt}]({src})")
        return

    # Recurse for other tags
    for child in element.children:
        _walk(child, lines)


def _inline_text(element: Tag) -> str:
    """Convert inline elements to markdown text."""
    parts: list[str] = []
    for child in element.children:
        if isinstance(child, str):
            parts.append(child.strip())
        elif isinstance(child, Tag):
            text = child.get_text(strip=True)
            if not text:
                continue
            if child.name in ("strong", "b"):
                parts.append(f"**{text}**")
            elif child.name in ("em", "i"):
                parts.append(f"*{text}*")
            elif child.name == "code":
                parts.append(f"`{text}`")
            elif child.name == "a":
                href = child.get("href", "")
                parts.append(f"[{text}]({href})" if href else text)
            elif child.name == "br":
                parts.append("\n")
            else:
                parts.append(text)
    return " ".join(p for p in parts if p)
