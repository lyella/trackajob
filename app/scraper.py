"""Job post scraping from a pasted URL.

Strategy, in order of reliability:

1. schema.org JobPosting JSON-LD. LinkedIn, Indeed, Kalibrr, JobStreet and
   most modern career sites publish this for Google Jobs, so it is the most
   structured and most stable source.
2. Open Graph / meta tags for title and company.
3. Site-specific selectors for the boards we know.
4. Generic heuristics: the largest text block that looks like a description.

The scraper is deliberately defensive. It runs server side against
user-supplied URLs, so it is an SSRF surface: only http(s) is allowed, DNS
resolution is checked against private ranges, redirects are followed
manually with the same check at each hop, and the response is size- and
time-capped. Every failure returns a typed reason the UI can explain, never
a stack trace.

Boards that render client side (LinkedIn in particular) return a shell page
to a plain HTTP client. When that happens we say so plainly and the UI falls
back to manual paste, which is always available. We never pretend a scrape
succeeded.
"""

from __future__ import annotations

import html as html_module
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

MAX_BYTES = 3_000_000
TIMEOUT = 12.0
MAX_REDIRECTS = 4
MAX_DESCRIPTION = 50_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# Hosts we recognise, for source labelling and for a clearer failure message.
KNOWN_BOARDS: dict[str, str] = {
    "linkedin.com": "LinkedIn",
    "indeed.com": "Indeed",
    "indeed.com.ph": "Indeed",
    "jobstreet.com": "JobStreet",
    "jobstreet.com.ph": "JobStreet",
    "kalibrr.com": "Kalibrr",
    "glassdoor.com": "Glassdoor",
    "glassdoor.com.ph": "Glassdoor",
    "jobsdb.com": "JobsDB",
    "seek.com.au": "Seek",
    "monster.com": "Monster",
    "ziprecruiter.com": "ZipRecruiter",
    "wellfound.com": "Wellfound",
    "angel.co": "Wellfound",
    "workday.com": "Workday",
    "greenhouse.io": "Greenhouse",
    "lever.co": "Lever",
    "myworkdayjobs.com": "Workday",
    "bamboohr.com": "BambooHR",
    "smartrecruiters.com": "SmartRecruiters",
    "upwork.com": "Upwork",
    "onlinejobs.ph": "OnlineJobs.ph",
    "jora.com": "Jora",
    "careerjet.com": "Careerjet",
    "trabajo.org": "Trabajo",
    "naukri.com": "Naukri",
    "bayt.com": "Bayt",
}

# Boards that serve an app shell to non-browser clients. Detected so we can
# explain the failure instead of returning an empty form.
JS_HEAVY = {"LinkedIn", "Indeed", "Glassdoor", "Wellfound", "Workday"}


class ScrapeError(Exception):
    """A failure with a client-safe message and a machine-readable reason."""

    def __init__(self, message: str, reason: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.status = status


@dataclass
class ScrapedJob:
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    source: str = ""
    salary: str = ""
    employment_type: str = ""
    posted: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "title": self.title.strip()[:200],
            "company": self.company.strip()[:150],
            "location": self.location.strip()[:150],
            "description": self.description.strip()[:MAX_DESCRIPTION],
            "url": self.url[:500],
            "source": self.source.strip()[:80],
            "salary": self.salary.strip()[:120],
            "employment_type": self.employment_type.strip()[:80],
            "posted": self.posted.strip()[:60],
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------
# URL safety
# --------------------------------------------------------------------------


def _is_public_host(hostname: str) -> bool:
    """Reject loopback, private, link-local and reserved addresses.

    A hostname that fails to resolve is allowed through so the request
    itself produces a clean network error rather than a confusing block.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def validate_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ScrapeError("Paste a job post link first.", "empty")
    # Reject a scheme we do not speak BEFORE adding https://, otherwise
    # "file:///etc/passwd" becomes "https://file:///etc/passwd" and slips
    # past the scheme check below.
    scheme_match = re.match(r"^([a-z][a-z0-9+.-]*):", url, re.I)
    if scheme_match:
        if scheme_match.group(1).lower() not in ("http", "https"):
            raise ScrapeError("Only http and https links can be imported.", "scheme")
    else:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ScrapeError("Only http and https links can be imported.", "scheme")
    if not parsed.hostname:
        raise ScrapeError("That does not look like a valid link.", "host")
    if not _is_public_host(parsed.hostname):
        raise ScrapeError("That address is not reachable from the server.", "private")
    return url


# Second-level labels that are part of a public suffix, so the registrable
# domain is the label before them ("somecompany.com.ph", not "com.ph").
_PUBLIC_SUFFIX_PARTS = {"co", "com", "org", "net", "gov", "edu", "ac", "or", "ne", "go"}


def _registrable_label(host: str) -> str:
    """The brand part of a hostname: careers.somecompany.com -> Somecompany."""
    host = host.lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if not parts:
        return ""
    # Drop the public suffix, which may be two labels for ccTLDs (com.ph).
    if len(parts) >= 3 and parts[-2] in _PUBLIC_SUFFIX_PARTS:
        parts = parts[:-2]
    else:
        parts = parts[:-1]
    if not parts:
        return host
    return parts[-1]


def board_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for domain, name in KNOWN_BOARDS.items():
        if host == domain or host.endswith("." + domain):
            return name
    label = _registrable_label(host)
    return label.title() if label else "Web"


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def fetch_html(url: str) -> tuple[str, str]:
    """Fetch with manual redirect handling so every hop is re-validated."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    current = url
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ScrapeError("The site redirected without a target.", "redirect")
                        current = validate_url(urljoin(current, location))
                        continue
                    if response.status_code >= 400:
                        raise ScrapeError(
                            f"The site returned HTTP {response.status_code}. "
                            "It may block automated visits. Paste the description instead.",
                            "http",
                        )
                    content_type = response.headers.get("content-type", "")
                    if "html" not in content_type and "xml" not in content_type:
                        raise ScrapeError(
                            "That link is not a web page. Paste the job description instead.",
                            "content-type",
                        )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_BYTES:
                            break
                        chunks.append(chunk)
                    return current, _decode(b"".join(chunks), content_type)
            except httpx.TimeoutException:
                raise ScrapeError(
                    "The site took too long to respond. Paste the description instead.", "timeout"
                )
            except httpx.HTTPError as exc:
                raise ScrapeError(
                    f"Could not reach that site ({type(exc).__name__}). "
                    "Paste the description instead.",
                    "network",
                )
    raise ScrapeError("Too many redirects.", "redirect")


def _decode(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    else:
        meta = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:2048], re.I)
        if meta:
            charset = meta.group(1).decode("ascii", "ignore")
    try:
        return raw.decode(charset, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _clean_text(value: str) -> str:
    """HTML to readable plain text, preserving paragraph breaks.

    JSON-LD descriptions arrive HTML-escaped (``&lt;p&gt;``), so the entity
    decode has to happen before the tag stripping or the tags survive as
    literal text.
    """
    if not value:
        return ""
    # Decode entities first: JSON-LD escapes its HTML, and a second pass is
    # harmless for already-plain text.
    value = html_module.unescape(value)
    if "<" in value and ">" in value:
        soup = BeautifulSoup(value, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for li in soup.find_all("li"):
            li.insert(0, "• ")
        # Inline emphasis must not split a sentence: unwrap it so the text
        # joins naturally, then add breaks only around block elements.
        for inline in soup.find_all(["strong", "b", "em", "i", "span", "a", "u"]):
            inline.unwrap()
        for block in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "tr", "ul", "ol"]):
            block.append("\n")
        value = soup.get_text("")
    value = html_module.unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t\u00a0]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    lines = [line.strip() for line in value.split("\n")]
    return "\n".join(lines).strip()


def _from_json_ld(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_json(data):
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if not any(isinstance(t, str) and "JobPosting" in t for t in types):
                continue
            org = node.get("hiringOrganization") or {}
            if isinstance(org, str):
                org = {"name": org}
            location = _ld_location(node)
            salary = _ld_salary(node)
            return {
                "title": str(node.get("title") or node.get("name") or ""),
                "company": str(org.get("name") or "") if isinstance(org, dict) else "",
                "location": location,
                "description": str(node.get("description") or ""),
                "salary": salary,
                "employment_type": _join(node.get("employmentType")),
                "posted": str(node.get("datePosted") or ""),
            }
    return None


def _walk_json(node):
    """Yield every dict in a possibly nested JSON-LD structure."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


def _join(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value) if value else ""


def _ld_location(node: dict) -> str:
    loc = node.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return ""
    address = loc.get("address")
    if isinstance(address, str):
        return address
    if not isinstance(address, dict):
        return str(loc.get("name") or "")
    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
    ]
    parts = [str(p) for p in parts if p and not isinstance(p, dict)]
    if not parts and isinstance(address.get("addressCountry"), dict):
        parts = [str(address["addressCountry"].get("name") or "")]
    return ", ".join(parts)


def _ld_salary(node: dict) -> str:
    salary = node.get("baseSalary")
    if not isinstance(salary, dict):
        return ""
    value = salary.get("value")
    currency = salary.get("currency") or ""
    if isinstance(value, dict):
        low, high = value.get("minValue"), value.get("maxValue")
        unit = value.get("unitText") or ""
        if low and high:
            return f"{currency} {low:,} – {high:,} {unit}".strip()
        if low or high:
            return f"{currency} {low or high} {unit}".strip()
    elif value:
        return f"{currency} {value}".strip()
    return ""


def _from_meta(soup: BeautifulSoup) -> dict:
    def meta(*names: str) -> str:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find(
                "meta", attrs={"name": name}
            )
            if tag and tag.get("content"):
                return str(tag["content"])
        return ""

    title = meta("og:title", "twitter:title") or (soup.title.string if soup.title else "")
    title = re.sub(r"\s*[|\-–—]\s*(LinkedIn|Indeed|JobStreet|Kalibrr|Glassdoor).*$", "", title or "", flags=re.I)
    return {
        "title": title.strip(),
        "company": meta("og:site_name", "author"),
        "description": meta("og:description", "description"),
    }


# Many boards put the employer in the <title> rather than a markup element:
# "L2 Operations Lead Job Openings at InnoVantage", "Engineer at Acme | Indeed".
_TITLE_COMPANY_PATTERNS = [
    r"\s+Job\s+Openings?\s+at\s+(.+)$",
    r"\s+at\s+([^|–—]+?)\s*(?:\||–|—|$)",
    r"\s+hiring\s+([^|–—]+?)\s*(?:\||–|—|$)",
    r"^(.+?)\s+job\s+in\s+.+$",
]


def _company_from_title(title: str) -> str:
    for pattern in _TITLE_COMPANY_PATTERNS:
        match = re.search(pattern, title or "", re.I)
        if match:
            candidate = match.group(1).strip(" -–—|")
            if 1 < len(candidate) < 80:
                return candidate
    return ""


def _title_tag(soup: BeautifulSoup) -> str:
    return (soup.title.string or "").strip() if soup.title else ""


# Site-specific selectors, tried after JSON-LD and meta.
SITE_SELECTORS: dict[str, dict[str, list[str]]] = {
    "LinkedIn": {
        "title": [".top-card-layout__title", ".topcard__title", "h1"],
        "company": [".topcard__org-name-link", ".top-card-layout__second-subline a"],
        "description": [".description__text", ".show-more-less-html__markup"],
    },
    "Indeed": {
        "title": [".jobsearch-JobInfoHeader-title", "h1.jobsearch-JobInfoHeader-title", "h1"],
        "company": ["[data-company-name]", ".jobsearch-InlineCompanyRating a"],
        "description": ["#jobDescriptionText", ".jobsearch-JobComponent-description"],
    },
    "JobStreet": {
        "title": ['[data-automation="job-detail-title"]', "h1"],
        "company": ['[data-automation="advertiser-name"]', '[data-automation="jobAdDetails"] h3'],
        "description": ['[data-automation="jobAdDetails"]', "article"],
    },
    "Kalibrr": {
        "title": ["h1", ".job-title"],
        "company": [".company-name", '[class*="company"] a'],
        "description": ['[class*="job-description"]', "article", "main"],
    },
    "Glassdoor": {
        "title": ['[data-test="job-title"]', "h1"],
        "company": ['[data-test="employer-name"]', '[class*="employer"]'],
        "description": [".jobDescriptionContent", '[class*="description"]'],
    },
}

GENERIC_SELECTORS = {
    "title": ["h1", '[class*="job-title" i]', '[class*="jobTitle" i]', '[itemprop="title"]'],
    "company": [
        '[class*="company-name" i]',
        '[class*="companyName" i]',
        '[itemprop="hiringOrganization"]',
        '[class*="employer" i]',
    ],
    "description": [
        '[class*="job-description" i]',
        '[class*="jobDescription" i]',
        '[id*="job-description" i]',
        '[id*="jobDescription" i]',
        '[class*="description" i]',
        "article",
        "main",
    ],
}


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> tuple[str, object]:
    for selector in selectors:
        try:
            node = soup.select_one(selector)
        except Exception:
            continue
        if node is None:
            continue
        text = node.get_text(" ", strip=True)
        if text and len(text) > 1:
            return text, node
    return "", None


def _largest_block(soup: BeautifulSoup) -> str:
    """Fallback: the densest text block on the page that is not navigation."""
    best = ""
    for node in soup.find_all(["div", "section", "article", "main"]):
        text = node.get_text(" ", strip=True)
        if 400 <= len(text) <= 60_000 and len(text) > len(best):
            best = text
    return best


def parse_job(html: str, url: str) -> ScrapedJob:
    soup = BeautifulSoup(html, "lxml")
    source = board_for(url)
    job = ScrapedJob(url=url, source=source)

    ld = _from_json_ld(soup)
    meta = _from_meta(soup)
    selectors = SITE_SELECTORS.get(source, GENERIC_SELECTORS)
    if source not in SITE_SELECTORS:
        selectors = GENERIC_SELECTORS

    def pick(key: str) -> str:
        text, _ = _first_text(soup, selectors.get(key, []))
        return text

    if ld:
        job.title = ld.get("title", "")
        job.company = ld.get("company", "")
        job.location = ld.get("location", "")
        job.description = _clean_text(ld.get("description", ""))
        job.salary = ld.get("salary", "")
        job.employment_type = ld.get("employment_type", "")
        job.posted = ld.get("posted", "")
        job.warnings.append("Read structured job data (schema.org) from the page.")

    if not job.title:
        job.title = pick("title") or meta.get("title", "")
    if not job.company:
        job.company = pick("company") or meta.get("company", "")
    if not job.company:
        # Last resort: the employer is often only in the <title>.
        job.company = _company_from_title(_title_tag(soup))
    if not job.description:
        job.description = _clean_text(pick("description"))
    if not job.description:
        job.description = _clean_text(_largest_block(soup))
        if job.description:
            job.warnings.append("Used the main text block; check the description carefully.")
    if not job.description:
        job.description = _clean_text(meta.get("description", ""))

    # A shell page has almost no body text: be honest rather than return junk.
    # Only judge the page as a shell when nothing usable was found, otherwise
    # a short but valid posting would be rejected.
    if len(job.description) < 200:
        body_text = soup.get_text(" ", strip=True)
        if len(body_text) < 1200:
            if source in JS_HEAVY:
                raise ScrapeError(
                    f"{source} loads job posts with JavaScript, so the text is not in the "
                    "page it sends us. Paste the description instead — it takes a moment.",
                    "javascript",
                )
            raise ScrapeError(
                "Could not find a job description on that page. Paste the description instead.",
                "not-found",
            )
        if not job.description:
            raise ScrapeError(
                "Could not find a job description on that page. Paste the description instead.",
                "not-found",
            )

    if not job.company:
        job.company = ""
        job.warnings.append("Company not found on the page; fill it in.")
    if not job.title:
        job.warnings.append("Role title not found; fill it in.")

    return job


def scrape(raw_url: str) -> ScrapedJob:
    url = validate_url(raw_url)
    final_url, html = fetch_html(url)
    job = parse_job(html, final_url)
    job.url = url  # keep the URL the user gave us
    return job
