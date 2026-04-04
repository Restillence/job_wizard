import re
import sys

from crawl4ai.async_configs import CrawlerRunConfig  # type: ignore

if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

JOB_CRAWL_CONFIG = CrawlerRunConfig(
    word_count_threshold=10,
    excluded_tags=["nav", "footer", "header", "aside", "form", "noscript"],
    excluded_selector=".cookie-banner, .sidebar, .related-jobs, .recommendations, .similar-jobs, [role='navigation'], [role='banner'], [role='contentinfo']",
    remove_overlay_elements=True,
    remove_forms=True,
    only_text=True,
    exclude_external_links=True,
    exclude_social_media_links=True,
)

_NOISE_PATTERNS = re.compile(
    r"(?mi)^.*\b(cookie|consent|privacy|datenschutz|impressum|newsletter|abonn|anmelden|registrier|sign[\s_-]?up|log[\s_-]?in|subscribe|tracking|werbung|advertisement|benutzername|passwort|pflichtfeld|bewerbungsübersicht|korrespondenz|zugangsdaten|talentpool|suchkriter|stelle merken|stelle drucken|stelle teilen|job abo|zurücksetzen|bitte warten|suchergebnis|nächste stelle|vorherige stelle|sprache wechseln|bewerbungsprozess|karriereportal|initiativbewerbung)\b.*$"
)
_IMG_PATTERN = re.compile(r"!\[[^\]]*\]\([^\)]+\)")
_LINK_ONLY_PATTERN = re.compile(r"^\[([^\]]*)\]\([^\)]+\)$", re.MULTILINE)
_URL_IN_BRACKETS = re.compile(r"^\s*\[.*\]\(https?://[^\s\)]+\)\s*$", re.MULTILINE)
_JOB_CONTENT_MARKERS = [
    re.compile(
        r"(?mi)(?:^#{1,3}\s+|\n).*\b(m/w/d|m/w/divers|full.?time|part.?time|senior|junior|lead|engineer|developer|manager|analyst|scientist|trainee|consultant)\b"
    ),
    re.compile(
        r"(?mi)(?:^#{1,3}\s+).*\b(job|stelle|aufgaben|profil|anforderungen|qualifikation|benefit|wir bieten|über uns|unternehmen|kontakt|bewerb|responsibilit|requirement|description|about the role)\b"
    ),
    re.compile(
        r"(?mi)^.*\b(art der stelle|standort|tätigkeitsfeld|datum des ersten|stellenart|beschäftigungsart|job type|location|department)\s*:"
    ),
]
_TAIL_NOISE_MARKERS = re.compile(
    r"(?mi)(?:^#{0,3}\s*\[?\s*|)\b(verwandte stellen|ähnliche stellen|related (?:jobs|positions|vacancies)|suchkriterien|suchergebn|fußzeile|footnote|footer|teilen über|share this|back to (?:search|results|jobs))\b"
)


def _sanitize_encoding(text: str) -> str:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = text.encode("utf-8", errors="replace").decode("utf-8")
    return text


def clean_markdown(md: str, max_chars: int = 12000) -> str:
    if not md:
        return ""

    md = _sanitize_encoding(md)

    md = _IMG_PATTERN.sub("", md)
    md = _LINK_ONLY_PATTERN.sub(r"\1", md)
    md = _URL_IN_BRACKETS.sub("", md)

    content_start = 0
    for pattern in _JOB_CONTENT_MARKERS:
        m = pattern.search(md)
        if m and (content_start == 0 or m.start() < content_start):
            content_start = m.start()
    if content_start > 200:
        md = md[content_start:]

    tail_match = _TAIL_NOISE_MARKERS.search(md)
    if tail_match and tail_match.start() > len(md) * 0.3:
        md = md[: tail_match.start()]

    md = _NOISE_PATTERNS.sub("", md)

    md = re.sub(r"\n{3,}", "\n\n", md)
    md = md.strip()
    if len(md) > max_chars:
        md = md[:max_chars]
    return md
