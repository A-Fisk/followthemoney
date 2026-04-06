from datetime import date
from pydantic import BaseModel


# ── Minimal embedded types ─────────────────────────────────────────────────────

class PartyMin(BaseModel):
    id: int
    name: str
    abbreviation: str | None = None


class DonorMin(BaseModel):
    id: int
    name: str
    industry_label: str | None = None
    needs_review: bool = False


class PoliticianMin(BaseModel):
    id: int
    name: str
    chamber: str | None = None
    electorate: str | None = None
    party: PartyMin | None = None


# ── List items ─────────────────────────────────────────────────────────────────

class PoliticianListItem(PoliticianMin):
    active: bool = True


class PartyListItem(BaseModel):
    id: int
    name: str
    abbreviation: str | None = None
    total_donations: float = 0.0


class DonorListItem(BaseModel):
    id: int
    name: str
    abn: str | None = None
    entity_type: str | None = None
    anzsic_code: str | None = None
    industry_label: str | None = None
    needs_review: bool = False


# ── Donation rows ──────────────────────────────────────────────────────────────

class DonationRow(BaseModel):
    """Used in politician + party detail: who gave."""
    id: int
    amount: float
    financial_year: str
    donation_type: str | None = None
    source_url: str | None = None
    donor: DonorMin | None = None


class DonationByPartyRow(BaseModel):
    """Used in donor detail: who received."""
    id: int
    amount: float
    financial_year: str
    donation_type: str | None = None
    source_url: str | None = None
    party: PartyMin | None = None
    politician_id: int | None = None
    politician_name: str | None = None


# ── Interest row ───────────────────────────────────────────────────────────────

class InterestRow(BaseModel):
    id: int
    description: str | None = None
    value_approx: float | None = None
    date_received: date | None = None
    date_declared: date | None = None
    days_late: int | None = None
    source_url: str | None = None
    donor: DonorMin | None = None


# ── Vote row ───────────────────────────────────────────────────────────────────

class VoteRow(BaseModel):
    id: int
    vote_direction: str
    vote_date: date | None = None
    bill_id: int
    bill_title: str
    issue_tags: list[str] | None = None
    theyvoteforyou_id: str | None = None


# ── Aggregation rows ───────────────────────────────────────────────────────────

class TopDonorRow(BaseModel):
    donor: DonorMin
    total: float


class PartyTotalRow(BaseModel):
    party: PartyMin
    total: float


class IndustryRow(BaseModel):
    industry_label: str
    total: float


class YearRow(BaseModel):
    financial_year: str
    total: float


class ExpenditureRow(BaseModel):
    financial_year: str
    category: str
    amount: float


# ── Detail responses ───────────────────────────────────────────────────────────

class PoliticianDetail(BaseModel):
    id: int
    name: str
    chamber: str | None = None
    electorate: str | None = None
    active: bool = True
    party: PartyMin | None = None
    direct_donations: list[DonationRow] = []
    interests: list[InterestRow] = []
    votes: list[VoteRow] = []


class PartyDetail(BaseModel):
    id: int
    name: str
    abbreviation: str | None = None
    total_donations: float = 0.0
    top_donors: list[TopDonorRow] = []
    industry_breakdown: list[IndustryRow] = []
    donations_by_year: list[YearRow] = []
    expenditure: list[ExpenditureRow] = []


class DonorDetail(BaseModel):
    id: int
    name: str
    abn: str | None = None
    entity_type: str | None = None
    anzsic_code: str | None = None
    industry_label: str | None = None
    controlling_person: str | None = None
    notes: str | None = None
    needs_review: bool = False
    total_donated: float = 0.0
    donations_by_party: list[PartyTotalRow] = []
    donations: list[DonationByPartyRow] = []


# ── Search ─────────────────────────────────────────────────────────────────────

class SearchResultItem(BaseModel):
    id: int
    name: str
    type: str           # "politician" | "party" | "donor"
    secondary: str | None = None   # party abbreviation / industry label


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]


# ── Unresolved ─────────────────────────────────────────────────────────────────

class UnresolvedDonor(BaseModel):
    id: int
    name: str
    entity_type: str | None = None
    total_donated: float = 0.0
    notes: str | None = None
