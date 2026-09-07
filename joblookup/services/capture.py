"""User-triggered public-page and pasted-alert capture, without account access."""

from __future__ import annotations

import json
import re
from email import policy
from email.parser import Parser
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from joblookup import store
from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.models import RawJob
from joblookup.sources.base import FetchContext, SourceAdapter, SourceError, check_outbound
from joblookup.sources.normalize import age_days, normalize, parse_date
from joblookup.sources.tier_b.access import blocked_url


class PublicPage(SourceAdapter):
    key = "manual"

    def fetch(self, context: FetchContext) -> list[RawJob]:
        return []


def safe_url(url: str) -> str:
    check_outbound(url)
    return url


def _location(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(filter(None, (_location(item) for item in value)))
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    address = value.get("address", value)
    if isinstance(address, str):
        return address
    return ", ".join(
        str(address[key])
        for key in ("addressLocality", "addressRegion", "addressCountry")
        if isinstance(address.get(key), str)
    )


def parse_page(html: str, url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        pending = value if isinstance(value, list) else [value]
        inspected = 0
        while pending and inspected < 100:
            item = pending.pop(0)
            inspected += 1
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("@graph"), list):
                pending.extend(item["@graph"][:100])
            types = item.get("@type") or []
            if "JobPosting" not in (types if isinstance(types, list) else [types]):
                continue
            organization = item.get("hiringOrganization") or {}
            salary = item.get("baseSalary") or {}
            salary = salary if isinstance(salary, dict) else {}
            value = salary.get("value") or {}
            value = value if isinstance(value, dict) else {"value": value}
            found.append(
                {
                    "title": str(item.get("title") or ""),
                    "company": str(organization.get("name") or "")
                    if isinstance(organization, dict)
                    else str(organization),
                    "description": BeautifulSoup(
                        str(item.get("description") or ""), "html.parser"
                    ).get_text("\n", strip=True),
                    "location": _location(
                        item.get("jobLocation") or item.get("applicantLocationRequirements")
                    ),
                    "url": url,
                    "posted_at": parse_date(item.get("datePosted")),
                    "valid_through": parse_date(item.get("validThrough")),
                    "work_mode": "remote"
                    if item.get("jobLocationType") == "TELECOMMUTE"
                    else "unknown",
                    "employment": "unknown",
                    "salary_min": value.get("minValue", value.get("value")),
                    "salary_max": value.get("maxValue", value.get("value")),
                    "salary_currency": salary.get("currency") or "",
                    "salary_period": str(value.get("unitText") or "").lower(),
                    "structured": True,
                }
            )
    return found[:30]


def fetch_page(url: str, settings: Settings) -> tuple[str, int, str]:
    safe_url(url)
    response = PublicPage().request(
        FetchContext(settings), url, headers={"accept": "text/html"}, allow_statuses={404, 410}
    )
    if len(response.content) > 4_000_000:
        raise SourceError("This page is too large to capture. Paste the job description instead.")
    if blocked_url(str(response.url)) or response.status_code in {401, 403, 429, 999}:
        raise SourceError(
            "The site requires sign-in or blocked public access. "
            "Capture the page in your browser or paste its text."
        )
    return response.text, response.status_code, str(response.url)


def preview(text: str, url: str = "") -> list[dict[str, Any]]:
    if url:
        safe_url(url)
    try:
        packet = json.loads(text)
    except ValueError:
        packet = None
    if isinstance(packet, dict) and packet.get("format") == "joblookup-capture-v1":
        target = safe_url(str(packet.get("url") or url))
        structured = parse_page(str(packet.get("html") or ""), target)
        if structured:
            return structured
        return [
            {
                "url": target,
                "title": str(packet.get("title") or ""),
                "company": str(packet.get("company") or ""),
                "location": str(packet.get("location") or ""),
                "description": str(packet.get("text") or "")[:100_000],
            }
        ]
    if re.search(r"^Content-Type:", text, re.M | re.I):
        message = Parser(policy=policy.default).parsestr(text)
        parts = [
            part
            for part in message.walk()
            if part.get_content_type() in {"text/html", "text/plain"}
            and part.get_content_disposition() != "attachment"
        ]
        text = "\n".join(str(part.get_content()) for part in parts)
    structured = parse_page(text, url) if "<" in text else []
    if structured:
        return structured
    soup = BeautifulSoup(text, "html.parser")
    plain = soup.get_text("\n", strip=True)
    links = [
        (anchor.get_text(" ", strip=True), urljoin(url, str(anchor.get("href"))))
        for anchor in soup.select("a[href]")
    ]
    links.extend(
        ("", match.rstrip(".,);>")) for match in re.findall(r"https?://[^\s<>\"']+", plain)
    )
    if url:
        links.insert(0, ("", url))
    result = []
    seen = set()
    for title, target in links:
        if target in seen:
            continue
        try:
            safe_url(target)
        except (SourceError, ValueError):
            continue
        seen.add(target)
        result.append(
            {
                "url": target,
                "title": title,
                "company": "",
                "location": "",
                "description": plain[:100_000] if len(links) <= 1 else "",
            }
        )
        if len(result) >= 30:
            break
    return result or [
        {"url": url, "title": "", "company": "", "location": "", "description": plain[:100_000]}
    ]


def import_posting(values: dict[str, Any]) -> dict[str, Any]:
    safe_url(values["url"])
    raw = RawJob(
        source_key="manual",
        title=values["title"].strip(),
        company=values["company"].strip(),
        location=values.get("location", ""),
        description=values["description"].strip(),
        url=values["url"],
        posted_at=parse_date(values.get("posted_at")),
        work_mode=values.get("work_mode", "unknown"),
        employment=values.get("employment", "unknown"),
        salary_min=values.get("salary_min"),
        salary_max=values.get("salary_max"),
        salary_currency=values.get("salary_currency", ""),
        raw={"access": "manual", "user_supplied": True},
    )
    job_id, created = store.upsert_job(normalize(raw))
    period = values.get("salary_period") or ""
    if period in {"hour", "day", "week", "month", "year"}:
        with db.transaction() as conn:
            conn.execute("UPDATE job SET salary_period = ? WHERE id = ?", (period, job_id))
    return {"job_id": job_id, "created": created}


def check_availability(job_id: int, settings: Settings) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        raise ValueError("This job no longer exists.")
    try:
        html, status, final_url = fetch_page(job.get("url") or job.get("apply_url"), settings)
        entries = parse_page(html, final_url)
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        expired = any(
            entry.get("valid_through") and (age_days(entry["valid_through"]) or 0) > 0
            for entry in entries
        )
        closed = (
            status in {404, 410}
            or expired
            or bool(
                re.search(
                    r"\b(?:this (?:job|position|vacancy) "
                    r"(?:is no longer available|has been filled|has expired|is closed)|"
                    r"no longer accepting applications)\b",
                    text,
                    re.I,
                )
            )
        )
        state = "closed" if closed else "listed" if entries else "unknown"
        detail = (
            "The public posting is expired, closed, or missing."
            if closed
            else "The page publishes a job listing; acceptance of new applications is not verified."
            if entries
            else "The page loaded but current application availability could not be verified."
        )
    except SourceError as exc:
        state, detail = "unknown", str(exc)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE job SET availability = ?, checked_at = datetime('now'), "
            "availability_detail = ? WHERE id = ?",
            (state, detail, job_id),
        )
    return {"availability": state, "detail": detail}
