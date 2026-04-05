"""
Parliament House Register of Interests — ingestion script.

Covers both chambers:
  Senate  — JSON API (clean structured data)
  House   — PDF download + pdfplumber parsing

Usage:
    uv run scripts/ingest_register.py              # both chambers
    uv run scripts/ingest_register.py --senate     # Senate only
    uv run scripts/ingest_register.py --house      # House only
    uv run scripts/ingest_register.py --no-clear   # append/update mode

Senate API base: https://pbs-apim-aqcdgxhvaug7f8em.z01.azurefd.net/api
House PDFs:      https://www.aph.gov.au/-/media/03_Senators_and_Members/32_Members/Register/48p/...
"""

import argparse
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx
import pdfplumber
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)

APH_BASE = "https://www.aph.gov.au"
HOUSE_REGISTER_URL = f"{APH_BASE}/Senators_and_Members/Members/Register"
SENATE_API_BASE = "https://pbs-apim-aqcdgxhvaug7f8em.z01.azurefd.net/api"

PDF_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "register" / "pdfs"


# ── DB helpers ────────────────────────────────────────────────────────────────

_politician_cache: dict[str, int] = {}
_donor_cache: dict[str, int] = {}


def upsert_politician(cur, name: str, chamber: str | None = None, party: str | None = None) -> int:
    name = name.strip()
    if name in _politician_cache:
        return _politician_cache[name]
    cur.execute(
        """
        INSERT INTO politicians (name, chamber)
        VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE SET
            chamber = COALESCE(EXCLUDED.chamber, politicians.chamber)
        RETURNING id
        """,
        (name, chamber),
    )
    pid = cur.fetchone()[0]
    _politician_cache[name] = pid
    return pid


def upsert_donor(cur, name: str) -> int:
    name = name.strip()
    if name in _donor_cache:
        return _donor_cache[name]
    cur.execute(
        "INSERT INTO donors (name, needs_review) VALUES (%s, true) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (name,),
    )
    did = cur.fetchone()[0]
    _donor_cache[name] = did
    return did


def insert_interest(cur, *, politician_id, donor_id=None, description,
                    value_approx=None, date_received=None, date_declared=None,
                    source_url):
    cur.execute(
        """
        INSERT INTO interests
            (politician_id, donor_id, description, value_approx,
             date_received, date_declared, source_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (politician_id, donor_id, description, value_approx,
         date_received, date_declared, source_url),
    )


# ── Entity extraction ─────────────────────────────────────────────────────────

# Patterns to extract the providing entity from free-text descriptions
_PROVIDER_PATTERNS = [
    r"[Pp]rovided by (.+?)(?:\.|$)",
    r"[Pp]rovided by (.+?)(?:\bon\b|\.|$)",
    r"[Oo]rganised by (.+?)(?:\.|$)",
    r"[Ff]rom (.+?)(?:\s+-\s+|\.|$)",
    r"[Cc]ourtesy of (.+?)(?:\.|$)",
    r"[Ss]ponsored by (.+?)(?:\.|$)",
    r"[Hh]osted by (.+?)(?:\.|$)",
]

_DATE_PATTERN = re.compile(
    r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b"
)


def extract_provider(text: str) -> str | None:
    for pat in _PROVIDER_PATTERNS:
        m = re.search(pat, text)
        if m:
            entity = m.group(1).strip().rstrip(".,;")
            if len(entity) > 2:
                return entity
    return None


def extract_date(text: str) -> date | None:
    m = _DATE_PATTERN.search(text)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_iso_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SENATE — JSON API
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all_senators(client: httpx.Client) -> list[dict]:
    senators = []
    page = 1
    while True:
        resp = client.get(f"{SENATE_API_BASE}/queryStatements", params={"pageSize": 100, "page": page})
        resp.raise_for_status()
        data = resp.json()
        senators.extend(data["statementOfRegisterableInterests"])
        if page >= data["pageCount"]:
            break
        page += 1
        time.sleep(0.3)
    return senators


def ingest_senator(cur, senator: dict, client: httpx.Client) -> int:
    cdapid = senator["cdapId"]
    name_raw = senator["name"]  # "Waters, Larissa"
    # Normalise to "Firstname Lastname"
    parts = [p.strip() for p in name_raw.split(",", 1)]
    name = f"{parts[1]} {parts[0]}" if len(parts) == 2 else name_raw

    party = senator.get("senatorParty", "")
    source_url = f"https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests/Senators_Interests_Register"

    resp = client.get(f"{SENATE_API_BASE}/getSenatorStatement", params={"cdapid": cdapid})
    resp.raise_for_status()
    data = resp.json()

    politician_id = upsert_politician(cur, name, chamber="senate")
    count = 0

    def process_section(section_key: str, detail_field: str):
        nonlocal count
        section = data.get(section_key, {})

        # Base interests
        for item in section.get("interests", []):
            desc = (item.get(detail_field) or "").strip()
            if not desc or desc.lower() == "not applicable":
                continue
            provider = extract_provider(desc)
            donor_id = upsert_donor(cur, provider) if provider else None
            insert_interest(
                cur,
                politician_id=politician_id,
                donor_id=donor_id,
                description=desc,
                source_url=source_url,
            )
            count += 1

        # Alterations (updates declared after initial lodgement)
        for alt in section.get("alterations", []):
            if alt.get("alterationType") != "Addition":
                continue
            desc = alt.get("details", "").strip()
            if not desc or desc.lower() == "not applicable":
                continue
            date_declared = parse_iso_date(alt.get("createdOn"))
            date_received = extract_date(desc)
            provider = extract_provider(desc)
            donor_id = upsert_donor(cur, provider) if provider else None
            insert_interest(
                cur,
                politician_id=politician_id,
                donor_id=donor_id,
                description=desc,
                date_received=date_received,
                date_declared=date_declared,
                source_url=source_url,
            )
            count += 1

    process_section("gifts", "detailOfGift")
    process_section("sponsoredTravelOrHospitality", "detailOfTravelHospitality")

    return count


def ingest_senate(cur) -> int:
    print("Senate register (JSON API) ...")
    total = 0
    with httpx.Client(timeout=30) as client:
        senators = fetch_all_senators(client)
        print(f"  {len(senators)} senators found")
        for i, senator in enumerate(senators, 1):
            n = ingest_senator(cur, senator, client)
            if n:
                print(f"  [{i:>2}/{len(senators)}] {senator['name']:<40} {n} entries")
            time.sleep(0.3)
            total += n
    return total


# ══════════════════════════════════════════════════════════════════════════════
# HOUSE — PDF scraping
# ══════════════════════════════════════════════════════════════════════════════

def fetch_house_pdf_links(client: httpx.Client) -> list[dict]:
    """Scrape the House register index page for all PDF links and MP names."""
    resp = client.get(HOUSE_REGISTER_URL)
    resp.raise_for_status()
    html = resp.text

    entries = []
    # Pattern: <a href="/-/media/.../Lastname_48P.pdf">Name (Electorate)</a>
    # alongside a "Last updated" span
    link_pattern = re.compile(
        r'href="(/-/media/[^"]+\.pdf)"[^>]*>\s*([^<]+)</a>',
        re.IGNORECASE,
    )
    # Also try to grab MP name from nearby text
    block_pattern = re.compile(
        r'href="(/-/media/03_Senators_and_Members/32_Members/Register[^"]+\.pdf)"',
        re.IGNORECASE,
    )

    seen = set()
    for m in block_pattern.finditer(html):
        pdf_path = m.group(1)
        if pdf_path in seen:
            continue
        seen.add(pdf_path)
        # Extract name from filename: "Albanese_48P.pdf" → "Albanese"
        filename = Path(pdf_path).stem  # e.g. "Albanese_48P" or "Andrew_Leigh_48P"
        name_part = filename.replace("_48P", "").replace("48P", "")
        # Try to find the MP name in surrounding HTML
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 100)
        surrounding = html[start:end]
        # Look for name in <a> tag text near this href
        name_match = re.search(r'>([A-Z][^<]{3,50}MP[^<]*)<', surrounding)
        display_name = name_match.group(1).strip() if name_match else name_part

        entries.append({
            "pdf_url": f"{APH_BASE}{pdf_path}",
            "filename_stem": name_part,
            "display_name": display_name,
        })

    return entries


def normalise_mp_name(display_name: str, filename_stem: str) -> str:
    """
    Best-effort: extract clean name from display strings like
    'Hon Anthony Albanese MP', 'Dr Monique Ryan MP', etc.
    Falls back to the filename stem.
    """
    name = display_name
    # Strip titles
    name = re.sub(r"^(Hon|Dr|Mr|Mrs|Ms|Prof|Senator|The Hon\.?)\s+", "", name, flags=re.IGNORECASE)
    # Strip trailing MP / party info
    name = re.sub(r"\s+MP\s*$", "", name, flags=re.IGNORECASE)
    name = name.strip()
    if len(name) < 3:
        # Fall back to filename stem, convert underscores to spaces
        name = filename_stem.replace("_", " ").title()
    return name


def download_pdf(url: str, dest: Path, client: httpx.Client) -> bool:
    if dest.exists():
        return True  # cached
    try:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    WARN: could not download {url}: {e}", file=sys.stderr)
        return False


# PDF section markers
_SECTION_HEADERS = {
    11: re.compile(r"11\s*\.\s*Gifts?", re.IGNORECASE),
    12: re.compile(r"12\s*\.\s*(Any\s+)?[Ss]ponsored\s+[Tt]ravel", re.IGNORECASE),
}

# Alteration page marker
_ALTERATION_HEADER = re.compile(r"NOTIFICATION OF ALTERATION", re.IGNORECASE)
_SUBMITTED_DATE = re.compile(r"Submitted Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
_PROCESSED_DATE = re.compile(r"Processed by Registrar[^:]*:\s*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)

# Row markers within sections
_SELF_MARKER = re.compile(r"^Self\s+(.+)", re.MULTILINE)
_SPOUSE_MARKER = re.compile(r"^Spouse/\s*\n?Partner\s+(.+)", re.MULTILINE)
_NOT_APPLICABLE = re.compile(r"not applicable", re.IGNORECASE)

# Item type in alteration pages (e.g. "11. Gifts" or "12. Travel Or Hospitality")
_ALTERATION_ITEM = re.compile(
    r"(11\.\s*Gifts?|12\.\s*(?:Travel|Sponsored)[\w\s]*)",
    re.IGNORECASE,
)


def parse_base_section(text: str, section_num: int) -> list[str]:
    """
    Extract all non-'Not Applicable' entries from section 11 or 12 of the
    base declaration pages.
    Returns a list of description strings (one per declared item).
    """
    header_re = _SECTION_HEADERS.get(section_num)
    if not header_re:
        return []

    m = header_re.search(text)
    if not m:
        return []

    # Find the next section header to bound the search
    next_section_re = re.compile(r"\n\d+\s*\.\s*[A-Z]")
    end_match = next_section_re.search(text, m.end())
    section_text = text[m.end(): end_match.start() if end_match else len(text)]

    entries = []
    # Split on row labels; collect content after "Self" and "Spouse/Partner"
    lines = section_text.split("\n")
    in_entry = False
    current = []
    for line in lines:
        line = line.rstrip()
        if re.match(r"^Self\s*$", line) or re.match(r"^Self\s+", line):
            if current:
                text_block = " ".join(current).strip()
                if text_block and not _NOT_APPLICABLE.search(text_block):
                    entries.append(text_block)
            current = [re.sub(r"^Self\s*", "", line).strip()]
            in_entry = True
        elif re.match(r"^Spouse/", line) or re.match(r"^Dependent", line):
            if current:
                text_block = " ".join(current).strip()
                if text_block and not _NOT_APPLICABLE.search(text_block):
                    entries.append(text_block)
            current = []
            in_entry = False
        elif in_entry and line:
            current.append(line)

    if current:
        text_block = " ".join(current).strip()
        if text_block and not _NOT_APPLICABLE.search(text_block):
            entries.append(text_block)

    return entries


def parse_alteration_page(text: str) -> list[dict]:
    """
    Parse a single alteration notification page.
    Returns list of dicts: {description, date_declared, item_type}
    """
    if not _ALTERATION_HEADER.search(text):
        return []

    # Only care about ADDITION blocks with items 11 or 12
    # Find "ADDITION" section
    add_match = re.search(r"ADDITION", text)
    del_match = re.search(r"DELETION", text)
    if not add_match:
        return []

    add_end = del_match.start() if del_match and del_match.start() > add_match.start() else len(text)
    addition_block = text[add_match.end(): add_end]

    # Find submitted date
    date_declared = None
    dm = _SUBMITTED_DATE.search(text)
    if dm:
        date_declared = extract_date(dm.group(1))

    results = []
    # Look for item 11 or 12 entries
    # The format is: "Item  Details\nSelf  <item type>  <description>"
    # or within the Self row: "12. Travel Or Hospitality  <description text>"
    item_matches = list(_ALTERATION_ITEM.finditer(addition_block))
    if not item_matches:
        return []

    for i, item_m in enumerate(item_matches):
        item_type = item_m.group(0).strip()
        # Description follows the item type on the same or next lines
        start = item_m.end()
        end = item_matches[i + 1].start() if i + 1 < len(item_matches) else len(addition_block)
        desc_raw = addition_block[start:end].strip()
        # Clean up multiline artefacts
        desc = re.sub(r"\s+", " ", desc_raw).strip()
        # Remove trailing "Spouse/ Partner Dependent Children" boilerplate
        desc = re.sub(r"\s*(Spouse/\s*Partner|Dependent\s*Children).*$", "", desc, flags=re.DOTALL).strip()
        if desc and not _NOT_APPLICABLE.search(desc):
            results.append({
                "description": desc,
                "date_declared": date_declared,
                "item_type": item_type,
            })

    return results


def parse_house_pdf(pdf_path: Path) -> list[dict]:
    """
    Parse a House register PDF.
    Returns list of interest dicts:
      {description, date_received, date_declared, interest_type}
    where interest_type is 'gift' or 'travel_hospitality'
    """
    entries = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(p.extract_text() or "" for p in pdf.pages[:7])
            alteration_pages = [
                p.extract_text() or ""
                for p in pdf.pages[7:]
            ]

        # Base sections (initial declaration)
        for section_num, interest_type in [(11, "gift"), (12, "travel_hospitality")]:
            for desc in parse_base_section(full_text, section_num):
                entries.append({
                    "description": desc,
                    "date_received": extract_date(desc),
                    "date_declared": None,
                    "interest_type": interest_type,
                })

        # Alteration notifications
        for page_text in alteration_pages:
            for alt in parse_alteration_page(page_text):
                interest_type = (
                    "gift" if "gift" in alt["item_type"].lower()
                    else "travel_hospitality"
                )
                entries.append({
                    "description": alt["description"],
                    "date_received": extract_date(alt["description"]),
                    "date_declared": alt["date_declared"],
                    "interest_type": interest_type,
                })

    except Exception as e:
        print(f"    WARN: PDF parse error for {pdf_path.name}: {e}", file=sys.stderr)

    return entries


def ingest_house(cur) -> int:
    print("House register (PDFs) ...")
    PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    with httpx.Client(timeout=30, headers={"User-Agent": "FollowTheMoney/1.0 (public interest research)"}) as client:
        entries = fetch_house_pdf_links(client)
        print(f"  {len(entries)} members found")

        for i, entry in enumerate(entries, 1):
            pdf_path = PDF_CACHE_DIR / f"{entry['filename_stem']}.pdf"
            if not download_pdf(entry["pdf_url"], pdf_path, client):
                continue

            mp_name = normalise_mp_name(entry["display_name"], entry["filename_stem"])
            politician_id = upsert_politician(cur, mp_name, chamber="house")

            interests = parse_house_pdf(pdf_path)
            for item in interests:
                provider = extract_provider(item["description"])
                donor_id = upsert_donor(cur, provider) if provider else None
                insert_interest(
                    cur,
                    politician_id=politician_id,
                    donor_id=donor_id,
                    description=item["description"],
                    date_received=item.get("date_received"),
                    date_declared=item.get("date_declared"),
                    source_url=entry["pdf_url"],
                )

            if interests:
                print(f"  [{i:>3}/{len(entries)}] {mp_name:<40} {len(interests)} entries")

            total += len(interests)
            time.sleep(0.5)  # be polite to aph.gov.au

    return total


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest Register of Interests data")
    parser.add_argument("--senate",   action="store_true", help="Senate only")
    parser.add_argument("--house",    action="store_true", help="House only")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear existing interests data")
    args = parser.parse_args()

    do_senate = args.senate or (not args.senate and not args.house)
    do_house  = args.house  or (not args.senate and not args.house)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                if not args.no_clear:
                    print("Clearing existing interests data ...")
                    cur.execute("TRUNCATE interests RESTART IDENTITY")
                    _politician_cache.clear()
                    _donor_cache.clear()

                total = 0
                if do_senate:
                    total += ingest_senate(cur)
                if do_house:
                    total += ingest_house(cur)

        print(f"\n{'─' * 50}")
        print(f"  Total interest entries loaded: {total:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
