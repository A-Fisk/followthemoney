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

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)

APH_BASE = "https://www.aph.gov.au"
HOUSE_REGISTER_URL = f"{APH_BASE}/Senators_and_Members/Members/Register"
SENATE_API_BASE = "https://pbs-apim-aqcdgxhvaug7f8em.z01.azurefd.net/api"

PDF_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "register" / "pdfs"
OCR_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "register" / "ocr_cache"
LLM_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "register" / "llm_cache"


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
    """Parse ISO-ish date strings including the API's '8/11/2025 2:00:00 PM' format."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.split("+")[0].strip(), fmt).date()
        except ValueError:
            continue
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
    # Use statement-level lodgement date as proxy date_declared for base interests
    # (the initial form has no per-item timestamps)
    lodgement_date = parse_iso_date(
        data.get("senatorInterestStatement", {}).get("lodgementDate")
    )
    count = 0

    def process_section(section_key: str, detail_field: str):
        nonlocal count
        section = data.get(section_key, {})

        # Base interests — declared no later than lodgement date
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
                date_declared=lodgement_date,
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
        # Extract name from filename stem as fallback
        filename = Path(pdf_path).stem  # e.g. "Albanese_48P" or "Andrew_Leigh_48P"
        name_part = filename.replace("_48P", "").replace("48P", "")
        # The MP name is in a <td> immediately before the PDF link cell.
        # Format: "LastName, Title FirstName, Member for Electorate, State"
        # Take the LAST <td>text</td> before the PDF href to avoid picking up
        # a cell from the previous row.
        start = max(0, m.start() - 300)
        surrounding = html[start:m.end()]
        td_matches = re.findall(r'<td>\s*([^<]+?)\s*</td>', surrounding)
        display_name = td_matches[-1].strip() if td_matches else name_part

        # Skip non-member entries (e.g. "Explanatory notes")
        if "member for" not in display_name.lower():
            continue

        entries.append({
            "pdf_url": f"{APH_BASE}{pdf_path}",
            "filename_stem": name_part,
            "display_name": display_name,
        })

    return entries


_TITLE_RE = re.compile(
    r"^(The\s+Hon\.?|Hon\.?|Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Miss\.?|Prof\.?)\s+",
    re.IGNORECASE,
)


def _strip_titles(s: str) -> str:
    """Strip one or more leading honorific titles."""
    prev = None
    while prev != s:
        prev = s
        s = _TITLE_RE.sub("", s).strip()
    return s


def normalise_mp_name(display_name: str, filename_stem: str) -> str:
    """
    Extract clean "FirstName LastName" from APH register table cell text.

    The cell format is: "LastName, Title FirstName, Member for Electorate, State"
    (Some entries use "." instead of "," after the last name.)
    Examples:
      "Albanese, Hon Anthony, Member for Grayndler, NSW"       → "Anthony Albanese"
      "Leigh, Hon Dr Andrew, Member for Fenner, ACT"           → "Andrew Leigh"
      "O'Brien, Mr Ted, Member for Fairfax, QLD"               → "Ted O'Brien"
      "France. Ms Ali, Member for Dickson, QLD"                → "Ali France"
    Falls back to the filename stem if parsing fails.
    """
    # Normalise: treat "LastName. " the same as "LastName, "
    normalised = re.sub(r"\.\s+", ", ", display_name, count=1)
    parts = [p.strip() for p in normalised.split(",")]
    if len(parts) >= 2:
        last_name = parts[0]
        given = _strip_titles(parts[1])
        if given and last_name:
            return f"{given} {last_name}"

    # Fallback: plain string cleanup
    name = display_name.strip()
    name = _strip_titles(name)
    name = re.sub(r",\s*Member\s+for.*$", "", name, flags=re.IGNORECASE)
    name = name.strip()
    if len(name) < 3:
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


def _split_chunk_lines(lines: list[str]) -> list[str]:
    """Return each non-empty line as a separate item (base-section helper)."""
    return [l.strip() for l in lines if l.strip()]


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
    lines = section_text.split("\n")
    in_entry = False
    chunk_lines: list[str] = []

    for line in lines:
        line = line.rstrip()
        if re.match(r"^Self\s*$", line) or re.match(r"^Self\s+", line):
            # Flush accumulated lines from previous Self block
            for item in _split_chunk_lines(chunk_lines):
                if not _NOT_APPLICABLE.search(item):
                    entries.append(item)
            first_content = re.sub(r"^Self\s*", "", line).strip()
            chunk_lines = [first_content] if first_content else []
            in_entry = True
        elif re.match(r"^Spouse/", line) or re.match(r"^Dependent", line):
            for item in _split_chunk_lines(chunk_lines):
                if not _NOT_APPLICABLE.search(item):
                    entries.append(item)
            chunk_lines = []
            in_entry = False
        elif in_entry and line:
            chunk_lines.append(line)

    for item in _split_chunk_lines(chunk_lines):
        if not _NOT_APPLICABLE.search(item):
            entries.append(item)

    return entries


def parse_alteration_page(page) -> list[dict]:
    """
    Parse a single alteration notification page using word-position analysis.

    Items in the right column (x ≥ RIGHT_COL_X) are grouped into physical lines
    by y-position, then split into individual interest items by y-gap > ITEM_GAP.
    This correctly handles both old-format (Albanese-style) and new-format
    (Wells-style) pages, including items that wrap across multiple PDF lines.

    Returns list of dicts: {description, date_declared, item_type}
    """
    text = page.extract_text() or ""
    if "ADDITION" not in text.upper():
        return []
    if not _ALTERATION_ITEM.search(text):
        return []

    # Submitted date from text (reliable in both formats)
    date_declared = None
    dm = _SUBMITTED_DATE.search(text)
    if dm:
        date_declared = extract_date(dm.group(1))

    words = page.extract_words()

    # ── Locate ADDITION / DELETION section y-bounds ──────────────────────────
    addition_y: float | None = None
    deletion_y: float = float("inf")
    for w in words:
        t = w["text"].upper()
        if t == "ADDITION" and addition_y is None:
            addition_y = w["top"]
        elif t == "DELETION" and addition_y is not None:
            deletion_y = w["top"]
            break

    if addition_y is None:
        return []

    # ── Determine right-column x boundary from "Details" header ──────────────
    # The "Details" header word marks the start of the right (description) column.
    # This varies by page format: ~159 for old-format, ~391 for new-format.
    RIGHT_COL_X = 140.0  # fallback
    for w in words:
        if w["top"] > addition_y and w["text"] == "Details":
            RIGHT_COL_X = w["x0"]
            break

    # ── Detect item type (11. Gifts / 12. Travel) from left-column label ─────
    item_type: str | None = None
    item_type_y: float | None = None

    for w in words:
        if w["top"] <= addition_y or w["top"] >= deletion_y:
            continue
        if w["x0"] < RIGHT_COL_X and re.match(r"1[12]\.", w["text"]):
            num = w["text"].rstrip(".")
            item_type = "11. Gifts" if num == "11" else "12. Travel Or Hospitality"
            item_type_y = w["top"]
            break  # use the FIRST item-type label found

    if item_type is None or item_type_y is None:
        return []

    # ── Find upper bounds (Spouse/Partner or Signed: row) ────────────────────
    stop_y: float = deletion_y
    for w in words:
        if w["top"] <= addition_y or w["top"] >= deletion_y:
            continue
        # "Spouse/" in left col, or "Signed:" anywhere — marks end of Self items
        if (w["x0"] < RIGHT_COL_X and w["text"].startswith("Spouse")) or w["text"].startswith("Signed"):
            stop_y = min(stop_y, w["top"])

    # ── Collect right-column words in the Self section ────────────────────────
    desc_words = [
        w for w in words
        if w["x0"] >= RIGHT_COL_X
        and w["top"] >= item_type_y - 5  # small tolerance for row alignment
        and w["top"] < stop_y
    ]
    if not desc_words:
        return []

    # ── Group words into text lines by y-position ─────────────────────────────
    LINE_TOL = 2.0  # words within 2 units share a line
    lines: list[tuple[float, list[str]]] = []
    for w in sorted(desc_words, key=lambda x: (x["top"], x["x0"])):
        if lines and abs(w["top"] - lines[-1][0]) <= LINE_TOL:
            lines[-1][1].append(w["text"])
        else:
            lines.append((w["top"], [w["text"]]))

    # ── Split lines into items by y-gap ───────────────────────────────────────
    # Within-item line spacing ≈ 12 units; between-item gap ≥ 15 units.
    ITEM_GAP = 13.0
    items: list[list[str]] = []
    current: list[str] = []
    prev_y: float | None = None

    for y, line_words in lines:
        line_text = " ".join(line_words)
        if prev_y is not None and (y - prev_y) > ITEM_GAP:
            if current:
                items.append(current)
            current = [line_text]
        else:
            current.append(line_text)
        prev_y = y

    if current:
        items.append(current)

    results = []
    for item_lines in items:
        desc = " ".join(item_lines).strip()
        if desc and not _NOT_APPLICABLE.search(desc):
            results.append({
                "description": desc,
                "date_declared": date_declared,
                "item_type": item_type,
            })

    return results


# ── Docling OCR fallback for image-based alteration pages ─────────────────────

_OCR_ITEM_LABEL_RE = re.compile(
    r"(1[12]\.\s*(?:Gifts?|Sponsored\s+travel[\w ]*|Travel[\w ]*))",
    re.IGNORECASE,
)
_HANGING_LINE = re.compile(
    r"(?:,|-|\b(?:of|the|from|a|an|and|or|in|at|to|by|for|new|\d+)|[A-Z]\.)$",
    re.IGNORECASE,
)


def _ocr_pdf(pdf_path: Path) -> dict[int, str]:
    """
    Run docling OCR on a PDF and return {1-based page_no: text}.
    Results are cached to OCR_CACHE_DIR/<stem>.json so subsequent
    ingestion runs don't re-OCR the same file.
    """
    import json

    OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = OCR_CACHE_DIR / f"{pdf_path.stem}.json"

    if cache_file.exists():
        return {int(k): v for k, v in json.loads(cache_file.read_text()).items()}

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.document import TextItem
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = True
        opts.do_table_structure = False

        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
        result = converter.convert(str(pdf_path))

        page_texts: dict[int, list[str]] = {}
        for item, _ in result.document.iterate_items():
            if not isinstance(item, TextItem):
                continue
            for prov in item.prov or []:
                page_texts.setdefault(prov.page_no, []).append(item.text)

        out = {pg: "\n".join(lines) for pg, lines in page_texts.items()}
        cache_file.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    except Exception as e:
        print(f"    WARN: docling OCR failed for {pdf_path.name}: {e}", file=sys.stderr)
        return {}


def llm_parse_alteration_page(text: str, date_declared, cache_key: str) -> list[dict]:
    """
    LLM fallback for alteration pages where the rules-based parser returns 0 items.

    Calls the configured LLM (see .env: LLM_BASE_URL / LLM_MODEL / LLM_API_KEY)
    and asks it to extract structured gift/travel records from the raw OCR text.
    Results are cached to LLM_CACHE_DIR so re-ingestion doesn't re-call the API.

    Returns the same format as parse_alteration_page_text:
        [{description, date_declared, item_type}, ...]
    """
    import json
    import hashlib

    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = LLM_CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    # Import lazily so the rest of the script works without LLM_API_KEY set
    try:
        from llm_client import chat_json, LLM_MODEL
    except EnvironmentError as e:
        print(f"  [LLM] Skipping — {e}", file=sys.stderr)
        return []

    prompt = f"""\
You are parsing an Australian politician's Register of Interests alteration page.
Extract all declared gifts and sponsored travel/hospitality items from the text below.

Return JSON with a single key "items", containing a list of objects with:
  - "description": full description of the gift or trip (string)
  - "item_type": either "11. Gifts" or "12. Travel Or Hospitality"
  - "date_received": date received in YYYY-MM-DD format if mentioned, else null
  - "provider": name of the person/organisation that gave the gift, if mentioned, else null

Only include items in the ADDITION section. Ignore DELETION entries and signature blocks.
If there are no items, return {{"items": []}}.

Raw text:
---
{text[:4000]}
---"""

    try:
        result = chat_json(
            [{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        items = result.get("items", [])
    except Exception as e:
        print(f"  [LLM] Error: {e}", file=sys.stderr)
        items = []

    # Normalise to the standard format expected by the caller
    output = []
    for item in items:
        desc = (item.get("description") or "").strip()
        if not desc:
            continue
        # Append provider to description if separate (mirrors how manual entries look)
        provider = (item.get("provider") or "").strip()
        if provider and provider.lower() not in desc.lower():
            desc = f"{desc} — {provider}"
        output.append({
            "description": desc,
            "date_declared": date_declared,
            "item_type": item.get("item_type") or "11. Gifts",
        })

    cache_file.write_text(json.dumps(output))
    return output


def parse_alteration_page_text(text: str, date_declared) -> list[dict]:
    """
    Parse a single alteration page whose text came from docling OCR.

    Docling preserves item-type labels ("11. Gifts", "12. Sponsored travel…")
    as text within the extracted content, so we split on those labels and
    attribute the following lines to the correct category.

    Returns list of dicts: {description, date_declared, item_type}
    """
    # Trim to ADDITION section only (stop at DELETION or Signed:)
    m = re.search(r"\bADDITION\b", text)
    if not m:
        return []
    content = text[m.end():]
    # Chop off at DELETION section or signature block
    content = re.split(r"\bDELETION\b", content, maxsplit=1)[0]
    content = re.sub(r"Signed:.*$", "", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r"\b(Details?|Item)\b\s*", "", content)

    # Split on item-type labels; odd indices are labels, even are content blocks
    parts = _OCR_ITEM_LABEL_RE.split(content)

    results = []
    current_type: str | None = None

    for part in parts:
        if _OCR_ITEM_LABEL_RE.fullmatch(part.strip()):
            current_type = "11. Gifts" if part.strip().startswith("11") else "12. Travel Or Hospitality"
            continue

        if current_type is None or not part.strip():
            continue

        # Join continuation lines.
        # A line is a continuation if the previous line ends with a comma,
        # hyphen, or a hanging preposition/article/conjunction/number.
        lines = [l.strip() for l in part.split("\n") if l.strip()]
        pending: str | None = None
        for line in lines:
            if pending is None:
                pending = line
            elif _HANGING_LINE.search(pending) or line.startswith("("):
                pending = pending + " " + line
            else:
                if not _NOT_APPLICABLE.search(pending):
                    results.append({
                        "description": pending,
                        "date_declared": date_declared,
                        "item_type": current_type,
                    })
                pending = line
        if pending and not _NOT_APPLICABLE.search(pending):
            results.append({
                "description": pending,
                "date_declared": date_declared,
                "item_type": current_type,
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

            # Base sections (initial declaration) — text-based, done while file is open
            for section_num, interest_type in [(11, "gift"), (12, "travel_hospitality")]:
                for desc in parse_base_section(full_text, section_num):
                    entries.append({
                        "description": desc,
                        "date_received": extract_date(desc),
                        "date_declared": None,
                        "interest_type": interest_type,
                    })

            # Alteration notifications — word-position parsing for text pages,
            # docling OCR fallback for image-only (scanned) pages.
            image_page_nums: list[int] = []  # 1-based, matching docling convention
            for page in pdf.pages[7:]:
                alts = parse_alteration_page(page)
                if alts:
                    for alt in alts:
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
                elif not page.extract_words() and page.images:
                    # Image-only page — queue for OCR
                    image_page_nums.append(page.page_number)

        # Run docling OCR on any image-only alteration pages
        if image_page_nums:
            print(f"      OCR: {len(image_page_nums)} image pages in {pdf_path.name} …",
                  end=" ", flush=True)
            ocr_pages = _ocr_pdf(pdf_path)
            print("done")
            for pg_num in image_page_nums:
                page_text = ocr_pages.get(pg_num, "")
                if not page_text:
                    continue
                # Extract submitted date from text
                date_declared = None
                dm = _SUBMITTED_DATE.search(page_text)
                if dm:
                    date_declared = extract_date(dm.group(1))
                alts = parse_alteration_page_text(page_text, date_declared)
                if not alts:
                    # Rules-based parser got nothing — try LLM fallback
                    cache_key = f"{pdf_path.stem}_p{pg_num}"
                    alts = llm_parse_alteration_page(page_text, date_declared, cache_key)
                    if alts:
                        print(f"      LLM extracted {len(alts)} item(s) from p{pg_num}")
                for alt in alts:
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
                    # Only clear interests for the chamber(s) being re-ingested,
                    # so --house doesn't wipe senate data and vice-versa.
                    if do_senate and do_house:
                        print("Clearing all interests data ...")
                        cur.execute("TRUNCATE interests RESTART IDENTITY")
                    elif do_senate:
                        print("Clearing senate interests data ...")
                        cur.execute("""
                            DELETE FROM interests WHERE politician_id IN (
                                SELECT id FROM politicians WHERE chamber = 'senate'
                            )
                        """)
                    elif do_house:
                        print("Clearing house interests data ...")
                        cur.execute("""
                            DELETE FROM interests WHERE politician_id IN (
                                SELECT id FROM politicians WHERE chamber = 'house'
                            )
                        """)
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
