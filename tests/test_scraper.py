"""Scraper tests.

Parsing is tested against saved HTML fixtures, not the live web: job boards
change their markup and rate-limit, so a network test would be flaky and
would fail for reasons that are not our bug. The URL-safety rules are tested
directly because they are the security boundary.
"""
import pytest

from app import scraper

# Real job pages carry a lot of chrome (nav, footer, related jobs). The
# fixtures include that bulk so they exercise the parser rather than the
# "is this a JavaScript shell?" heuristic.
_PAGE_BULK = (
    "<nav><a>Home</a><a>Jobs</a><a>Companies</a><a>Salaries</a></nav>"
    "<footer>" + ("Related jobs and company information. " * 40) + "</footer>"
)

LINKEDIN_JSONLD = f"""
<html><head><title>Senior Backend Engineer at Coins.ph | LinkedIn</title></head><body>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Senior Backend Engineer",
 "description":"&lt;p&gt;Build &lt;strong&gt;payment&lt;/strong&gt; systems.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Own the API&lt;/li&gt;&lt;li&gt;Mentor&lt;/li&gt;&lt;/ul&gt;",
 "datePosted":"2026-01-05",
 "employmentType":"FULL_TIME",
 "hiringOrganization":{{"@type":"Organization","name":"Coins.ph"}},
 "jobLocation":{{"@type":"Place","address":{{"@type":"PostalAddress",
   "addressLocality":"Taguig","addressCountry":"PH"}}}},
 "baseSalary":{{"@type":"MonetaryAmount","currency":"PHP",
   "value":{{"@type":"QuantitativeValue","minValue":120000,"maxValue":180000,"unitText":"MONTH"}}}}}}
</script>
{_PAGE_BULK}
</body></html>
"""

GRAPH_JSONLD = f"""
<html><head><title>Engineer</title></head><body>
<script type="application/ld+json">
{{"@context":"https://schema.org","@graph":[
  {{"@type":"WebSite","name":"Careers"}},
  {{"@type":"JobPosting","title":"Platform Engineer",
   "hiringOrganization":{{"name":"Canva"}},
   "description":"<p>Build the internal platform.</p><p>Kubernetes and Go.</p>"}}
]}}
</script>
{_PAGE_BULK}
</body></html>
"""

TITLE_ONLY = f"""
<html><head><title>L2 Operations Lead Job Openings at InnoVantage</title></head><body>
<h1>L2 Operations Lead</h1>
<div class="job-description">
<p>We are looking for an operations lead to run our platform.</p>
<p>You will own incident response and mentor the team on reliability.</p>
<p>Requirements: three years of production operations experience.</p>
</div>
{_PAGE_BULK}
</body></html>
"""

SHELL_PAGE = """
<html><head><title>Indeed</title></head><body>
<div id="root"></div>
<script>window.__DATA__ = {};</script>
</body></html>
"""


def test_parses_json_ld_job_posting():
    job = scraper.parse_job(LINKEDIN_JSONLD, "https://ph.linkedin.com/jobs/view/123")
    assert job.title == "Senior Backend Engineer"
    assert job.company == "Coins.ph"
    assert "Taguig" in job.location
    assert job.source == "LinkedIn"
    assert "PHP" in job.salary
    # Escaped HTML in the JSON-LD must become plain text, not literal tags.
    assert "<p>" not in job.description
    assert "&lt;" not in job.description
    assert "Build payment systems." in job.description
    assert "• Own the API" in job.description


def test_parses_json_ld_inside_graph():
    job = scraper.parse_job(GRAPH_JSONLD, "https://jobs.example.com/1")
    assert job.title == "Platform Engineer"
    assert job.company == "Canva"
    assert "internal platform" in job.description


def test_falls_back_to_title_for_company():
    job = scraper.parse_job(TITLE_ONLY, "https://www.kalibrr.com/c/x/jobs/1")
    assert job.company == "InnoVantage"
    assert job.title == "L2 Operations Lead"
    assert "incident response" in job.description


def test_shell_page_raises_javascript_error():
    with pytest.raises(scraper.ScrapeError) as exc:
        scraper.parse_job(SHELL_PAGE, "https://ph.indeed.com/viewjob?jk=1")
    assert exc.value.reason == "javascript"
    assert "Paste the description" in exc.value.message


def test_empty_page_raises_not_found():
    with pytest.raises(scraper.ScrapeError) as exc:
        scraper.parse_job("<html><body></body></html>", "https://example.com/job")
    assert exc.value.reason == "not-found"


def test_board_detection():
    assert scraper.board_for("https://ph.linkedin.com/jobs/view/1") == "LinkedIn"
    assert scraper.board_for("https://www.jobstreet.com.ph/job/1") == "JobStreet"
    assert scraper.board_for("https://ph.indeed.com/viewjob") == "Indeed"
    assert scraper.board_for("https://www.kalibrr.com/c/x/jobs/1") == "Kalibrr"
    assert scraper.board_for("https://boards.greenhouse.io/x/jobs/1") == "Greenhouse"
    assert scraper.board_for("https://careers.somecompany.com/job/1") == "Somecompany"


@pytest.mark.parametrize(
    "url,reason",
    [
        ("", "empty"),
        ("file:///etc/passwd", "scheme"),
        ("javascript:alert(1)", "scheme"),
        ("ftp://example.com/x", "scheme"),
        ("http://127.0.0.1/x", "private"),
        ("http://localhost:8000/x", "private"),
        ("http://169.254.169.254/latest/meta-data", "private"),
        ("http://10.0.0.5/x", "private"),
        ("http://192.168.1.1/x", "private"),
    ],
)
def test_unsafe_urls_are_rejected(url, reason):
    with pytest.raises(scraper.ScrapeError) as exc:
        scraper.validate_url(url)
    assert exc.value.reason == reason


def test_bare_domain_gets_https():
    assert scraper.validate_url("example.com/job/1") == "https://example.com/job/1"


def test_public_url_passes():
    assert scraper.validate_url("https://example.com/job/1") == "https://example.com/job/1"
