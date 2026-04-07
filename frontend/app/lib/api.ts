const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PartyMin {
  id: number;
  name: string;
  abbreviation: string | null;
}

export interface DonorMin {
  id: number;
  name: string;
  industry_label: string | null;
  needs_review: boolean;
}

export interface PoliticianMin {
  id: number;
  name: string;
  chamber: string | null;
  electorate: string | null;
  party: PartyMin | null;
  active: boolean;
}

export interface DonationRow {
  id: number;
  amount: number;
  financial_year: string;
  donation_type: string | null;
  source_url: string | null;
  donor: DonorMin | null;
}

export interface DonationByPartyRow {
  id: number;
  amount: number;
  financial_year: string;
  donation_type: string | null;
  source_url: string | null;
  party: PartyMin | null;
  politician_id: number | null;
  politician_name: string | null;
}

export interface InterestRow {
  id: number;
  description: string | null;
  value_approx: number | null;
  date_received: string | null;
  date_declared: string | null;
  days_late: number | null;
  source_url: string | null;
  donor: DonorMin | null;
}

export interface PolicyPosition {
  name: string;
  vote: "aye" | "no"; // direction that SUPPORTS this policy
}

export interface VoteRow {
  id: number;
  vote_direction: string;
  vote_date: string | null;
  bill_id: number;
  bill_title: string;
  issue_tags: string[] | null;
  policy_positions: PolicyPosition[] | null;
  theyvoteforyou_id: string | null;
  tvfy_house: string | null;
  tvfy_number: number | null;
}

export interface PartyBranchDonation extends DonationRow {
  party_id: number;
  party_name: string;
}

export interface AsDonorDonation {
  id: number;
  amount: number;
  financial_year: string;
  donation_type: string | null;
  source_url: string | null;
  donor_id: number;
  donor_name: string;
  recipient_party_id: number | null;
  recipient_party_name: string | null;
  recipient_politician_id: number | null;
  recipient_politician_name: string | null;
}

export interface PoliticianDetail extends PoliticianMin {
  party_top_donors: TopDonorRow[];
  direct_donations: DonationRow[];
  via_party_donations: PartyBranchDonation[];
  as_donor_donations: AsDonorDonation[];
  interests: InterestRow[];
  votes: VoteRow[];
}

export interface TopDonorRow {
  donor: DonorMin;
  total: number;
}

export interface PartyTotalRow {
  party: PartyMin;
  total: number;
}

export interface PartyDetail {
  id: number;
  name: string;
  abbreviation: string | null;
  total_donations: number;
  top_donors: TopDonorRow[];
  industry_breakdown: { industry_label: string; total: number }[];
  donations_by_year: { financial_year: string; total: number }[];
  expenditure: { financial_year: string; category: string; amount: number }[];
}

export interface DonorDetail {
  id: number;
  name: string;
  abn: string | null;
  entity_type: string | null;
  anzsic_code: string | null;
  industry_label: string | null;
  controlling_person: string | null;
  notes: string | null;
  needs_review: boolean;
  total_donated: number;
  donations_by_party: PartyTotalRow[];
  donations: DonationByPartyRow[];
}

export interface SearchResultItem {
  id: number;
  name: string;
  type: "politician" | "party" | "donor";
  secondary: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
}

export interface UnresolvedDonor {
  id: number;
  name: string;
  entity_type: string | null;
  total_donated: number;
  notes: string | null;
}

// ── Fetch functions ────────────────────────────────────────────────────────────

export const fetchPolitician = (id: string) =>
  apiFetch<PoliticianDetail>(`/api/v1/politicians/${id}`);

export const fetchParty = (id: string) =>
  apiFetch<PartyDetail>(`/api/v1/parties/${id}`);

export const fetchDonor = (id: string) =>
  apiFetch<DonorDetail>(`/api/v1/donors/${id}`);

export const fetchSearch = (q: string) =>
  apiFetch<SearchResponse>(`/api/v1/search?q=${encodeURIComponent(q)}&limit=15`);

export const fetchUnresolved = () =>
  apiFetch<UnresolvedDonor[]>(`/api/v1/unresolved?limit=200`);

export const csvUrl = (path: string) =>
  `${API_URL}${path}${path.includes("?") ? "&" : "?"}format=csv`;
