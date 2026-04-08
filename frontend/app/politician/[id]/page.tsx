import React from "react";
import { notFound } from "next/navigation";
import {
  fetchPolitician,
  VoteRow,
  PolicyPosition,
  TopDonorRow,
  DonationRow,
  PartyBranchDonation,
  AsDonorDonation,
  InterestRow,
} from "../../lib/api";

// ── Parliament ranges ─────────────────────────────────────────────────────────

const PARLIAMENTS: { number: number; start: string; end: string | null }[] = [
  { number: 47, start: "2022-07-26", end: null },
  { number: 46, start: "2019-07-02", end: "2022-07-25" },
  { number: 45, start: "2016-08-30", end: "2019-07-01" },
  { number: 44, start: "2013-11-12", end: "2016-08-29" },
  { number: 43, start: "2010-09-28", end: "2013-11-11" },
  { number: 42, start: "2008-02-12", end: "2010-09-27" },
  { number: 41, start: "2004-11-16", end: "2008-02-11" },
];

function voteParliament(voteDate: string | null): number | null {
  if (!voteDate) return null;
  for (const p of PARLIAMENTS) {
    if (voteDate >= p.start && (p.end === null || voteDate <= p.end)) return p.number;
  }
  return null;
}

// ── Sort types ────────────────────────────────────────────────────────────────

type PtdSort  = "donor"  | "industry" | "total";
type IntSort  = "description" | "provider" | "received" | "declared" | "days_late";
type DdSort   = "year"   | "amount"   | "donor"  | "industry";
type VpbSort  = "year"   | "amount"   | "donor"  | "branch";
type DmSort   = "year"   | "amount"   | "donor"  | "recipient";
type VoteSort = "date"   | "vote"     | "issue";

function sortTopDonors(rows: TopDonorRow[], s: PtdSort): TopDonorRow[] {
  return [...rows].sort((a, b) => {
    if (s === "donor")    return a.donor.name.localeCompare(b.donor.name);
    if (s === "industry") return (a.donor.industry_label ?? "").localeCompare(b.donor.industry_label ?? "");
    return b.total - a.total;
  });
}

function sortInterests(rows: InterestRow[], s: IntSort): InterestRow[] {
  return [...rows].sort((a, b) => {
    if (s === "description") return (a.description ?? "").localeCompare(b.description ?? "");
    if (s === "provider")    return (a.donor?.name ?? "").localeCompare(b.donor?.name ?? "");
    if (s === "received")    return (b.date_received ?? "").localeCompare(a.date_received ?? "");
    if (s === "days_late")   return (b.days_late ?? 0) - (a.days_late ?? 0);
    return (b.date_declared ?? "").localeCompare(a.date_declared ?? ""); // declared (default)
  });
}

function sortDonations(rows: DonationRow[], s: DdSort): DonationRow[] {
  return [...rows].sort((a, b) => {
    if (s === "amount")   return b.amount - a.amount;
    if (s === "donor")    return (a.donor?.name ?? "").localeCompare(b.donor?.name ?? "");
    if (s === "industry") return (a.donor?.industry_label ?? "").localeCompare(b.donor?.industry_label ?? "");
    return (b.financial_year ?? "").localeCompare(a.financial_year ?? ""); // year (default)
  });
}

function sortViaBranch(rows: PartyBranchDonation[], s: VpbSort): PartyBranchDonation[] {
  return [...rows].sort((a, b) => {
    if (s === "amount") return b.amount - a.amount;
    if (s === "donor")  return (a.donor?.name ?? "").localeCompare(b.donor?.name ?? "");
    if (s === "branch") return (a.party_name ?? "").localeCompare(b.party_name ?? "");
    return (b.financial_year ?? "").localeCompare(a.financial_year ?? "");
  });
}

function sortAsDonor(rows: AsDonorDonation[], s: DmSort): AsDonorDonation[] {
  return [...rows].sort((a, b) => {
    if (s === "amount")    return b.amount - a.amount;
    if (s === "donor")     return (a.donor_name ?? "").localeCompare(b.donor_name ?? "");
    if (s === "recipient") {
      const rA = a.recipient_party_name ?? a.recipient_politician_name ?? "";
      const rB = b.recipient_party_name ?? b.recipient_politician_name ?? "";
      return rA.localeCompare(rB);
    }
    return (b.financial_year ?? "").localeCompare(a.financial_year ?? "");
  });
}

function sortVotes(votes: VoteRow[], sort: VoteSort): VoteRow[] {
  return [...votes].sort((a, b) => {
    if (sort === "vote")  return (a.vote_direction ?? "").localeCompare(b.vote_direction ?? "");
    if (sort === "issue") return (a.issue_tags?.[0] ?? "zzz").localeCompare(b.issue_tags?.[0] ?? "zzz");
    return (b.vote_date ?? "").localeCompare(a.vote_date ?? "");
  });
}

// ── URL helpers ───────────────────────────────────────────────────────────────

function buildUrl(
  current: Record<string, string | undefined>,
  overrides: Record<string, string | undefined>
): string {
  const merged = { ...current, ...overrides };
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(merged)) {
    if (v) p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "?";
}

// ── Sort header helper ────────────────────────────────────────────────────────

function SortTh({
  label,
  sortKey,
  current,
  href,
  right,
}: {
  label: string;
  sortKey: string;
  current: string;
  href: string;
  right?: boolean;
}) {
  const active = current === sortKey;
  return (
    <th className={`py-2 pr-4 ${right ? "text-right" : ""}`}>
      <a
        href={href}
        className={active ? "font-semibold text-gray-800" : "text-gray-500 hover:text-gray-700"}
      >
        {label}{active ? " ↓" : ""}
      </a>
    </th>
  );
}

// ── Vote policy display ───────────────────────────────────────────────────────

function policyStance(positions: PolicyPosition[], voteDirection: string): React.ReactNode {
  return (
    <ul className="space-y-0.5">
      {positions.map((p) => {
        const supports = p.vote === voteDirection;
        return (
          <li key={p.name} className={supports ? "text-green-700" : "text-red-600"}>
            <span className="mr-1">{supports ? "✓" : "✗"}</span>
            {supports ? "supports" : "opposes"} {p.name}
          </li>
        );
      })}
    </ul>
  );
}

function tvfyUrl(v: VoteRow): string | null {
  if (v.tvfy_house && v.vote_date && v.tvfy_number != null) {
    return `https://theyvoteforyou.org.au/divisions/${v.tvfy_house}/${v.vote_date}/${v.tvfy_number}`;
  }
  return null;
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function PoliticianPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    sort?: string; parliament?: string; issue?: string; from?: string; to?: string;
    ptd?: string; int?: string; dd?: string; vpb?: string; dm?: string;
    ddl?: string; vpbl?: string; dml?: string; intl?: string; vl?: string;
  }>;
}) {
  const { id } = await params;
  const { sort, parliament, issue, from, to, ptd, int: intParam, dd, vpb, dm,
          ddl, vpbl, dml, intl, vl } = await searchParams;

  const voteSort:   VoteSort = sort === "vote" || sort === "issue" ? sort : "date";
  const ptdSort:    PtdSort  = ptd === "donor" || ptd === "industry" ? ptd : "total";
  const intSort:    IntSort  = intParam === "description" || intParam === "provider" || intParam === "received" || intParam === "days_late" ? intParam : "declared";
  const ddSort:     DdSort   = dd === "amount" || dd === "donor" || dd === "industry" ? dd : "year";
  const vpbSort:    VpbSort  = vpb === "amount" || vpb === "donor" || vpb === "branch" ? vpb : "year";
  const dmSort:     DmSort   = dm === "amount" || dm === "donor" || dm === "recipient" ? dm : "year";
  const selectedParliament   = parliament ? Number(parliament) : null;
  const selectedIssue        = issue ?? null;

  const pol = await fetchPolitician(id, { from_year: from, to_year: to });
  if (!pol) notFound();

  const chamberLabel = pol.chamber === "house" ? "House of Representatives" : pol.chamber === "senate" ? "Senate" : null;

  // Convert a date string to its financial year, e.g. "2019-09-15" → "2019-20"
  function dateToFY(date: string): string {
    const year = parseInt(date.slice(0, 4));
    const month = parseInt(date.slice(5, 7));
    const startYear = month >= 7 ? year : year - 1;
    return `${startYear}-${String(startYear + 1).slice(2)}`;
  }

  // from/to are financial years e.g. "2019-20"; convert to ISO date boundaries
  const fyStart = from ? `${from.split("-")[0]}-07-01` : null;
  const fyEnd   = to   ? `${parseInt(to.split("-")[0]) + 1}-06-30` : null;

  const parliamentsWithVotes = [
    ...new Set(pol.votes.map((v) => voteParliament(v.vote_date)).filter((n): n is number => n !== null)),
  ].sort((a, b) => b - a);

  const filteredVotes = pol.votes
    .filter((v) => !selectedParliament || voteParliament(v.vote_date) === selectedParliament)
    .filter((v) => !selectedIssue || v.issue_tags?.includes(selectedIssue))
    .filter((v) => !fyStart || (v.vote_date ?? "") >= fyStart)
    .filter((v) => !fyEnd   || (v.vote_date ?? "") <= fyEnd);

  const allIssueTags = [...new Set(
    pol.votes.flatMap((v) => v.issue_tags ?? [])
  )].sort();

  // All current params — passed to buildUrl so every sort link preserves the others
  const cp = { sort, parliament, issue, from, to, ptd, int: intParam, dd, vpb, dm,
               ddl, vpbl, dml, intl, vl };

  const DEFAULT_LIMIT = 10;
  const ddLimit   = ddl  === "all" ? Infinity : DEFAULT_LIMIT;
  const vpbLimit  = vpbl === "all" ? Infinity : DEFAULT_LIMIT;
  const dmLimit   = dml  === "all" ? Infinity : DEFAULT_LIMIT;
  const intLimit  = intl === "all" ? Infinity : DEFAULT_LIMIT;
  const voteLimit = vl   === "all" ? Infinity : DEFAULT_LIMIT;

  // Current financial year always available in "to" dropdown
  const now = new Date();
  const fyStartYear = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
  const currentFY = `${fyStartYear}-${String(fyStartYear + 1).slice(2)}`;

  // Find the earliest FY across all data sources
  const dataYears = [
    ...pol.votes.map((v) => v.vote_date ? dateToFY(v.vote_date) : null),
    ...pol.direct_donations.map((d) => d.financial_year),
    ...pol.via_party_donations.map((d) => d.financial_year),
    ...pol.as_donor_donations.map((d) => d.financial_year),
    ...pol.interests.map((i) => i.date_declared ? dateToFY(i.date_declared) : null),
  ].filter((y): y is string => !!y);

  // Generate a continuous range from earliest year to current FY
  const earliestFYStart = dataYears.length
    ? Math.min(...dataYears.map((y) => parseInt(y.split("-")[0])))
    : fyStartYear;
  const allYears: string[] = [];
  for (let y = earliestFYStart; y <= fyStartYear; y++) {
    allYears.push(`${y}-${String(y + 1).slice(2)}`);
  }

  const filteredDirectDons    = pol.direct_donations.filter((d) =>
    (!from || (d.financial_year ?? "") >= from) && (!to || (d.financial_year ?? "") <= to));
  const filteredViaBranchDons = pol.via_party_donations.filter((d) =>
    (!from || (d.financial_year ?? "") >= from) && (!to || (d.financial_year ?? "") <= to));
  const filteredAsDonorDons   = pol.as_donor_donations.filter((d) =>
    (!from || (d.financial_year ?? "") >= from) && (!to || (d.financial_year ?? "") <= to));
  const filteredInterests     = pol.interests.filter((i) =>
    (!fyStart || !i.date_declared || i.date_declared >= fyStart) &&
    (!fyEnd   || !i.date_declared || i.date_declared <= fyEnd));

  const topDonors         = sortTopDonors(pol.party_top_donors, ptdSort);
  const sortedInterests   = sortInterests(filteredInterests, intSort);
  const sortedDirectDons  = sortDonations(filteredDirectDons, ddSort);
  const sortedViaBranch   = sortViaBranch(filteredViaBranchDons, vpbSort);
  const sortedAsDonor     = sortAsDonor(filteredAsDonorDons, dmSort);

  const interests     = sortedInterests.slice(0, intLimit);
  const directDons    = sortedDirectDons.slice(0, ddLimit);
  const viaBranchDons = sortedViaBranch.slice(0, vpbLimit);
  const asDonorDons   = sortedAsDonor.slice(0, dmLimit);
  const sortedVotes   = sortVotes(filteredVotes, voteSort);
  const visibleVotes  = sortedVotes.slice(0, voteLimit);

  return (
    <div className="space-y-8">
      {/* Identity */}
      <div>
        <h1 className="text-2xl font-bold">{pol.name}</h1>
        <p className="mt-1 text-sm text-gray-600">
          {[chamberLabel, pol.electorate, pol.party?.name].filter(Boolean).join(" · ")}
        </p>
        <div className="mt-2 flex gap-3 text-xs">
          <a href={`/brief/${id}`} className="text-blue-600 hover:underline">
            Journalist briefing card →
          </a>
          {pol.party && (
            <a href={`/party/${pol.party.id}`} className="text-blue-600 hover:underline">
              {pol.party.abbreviation || pol.party.name} party profile →
            </a>
          )}
        </div>
      </div>

      {/* Year filter — applies to all sections */}
      {allYears.length > 1 && (
        <form method="GET" className="flex flex-wrap items-center gap-2 text-xs">
          {Object.entries(cp).filter(([k, v]) => v && k !== "from" && k !== "to").map(([k, v]) => (
            <input key={k} type="hidden" name={k} value={v} />
          ))}
          <span className="text-gray-400">Filter by year</span>
          <select name="from" defaultValue={from ?? ""}
            className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 bg-white">
            <option value="">From</option>
            {allYears.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <span className="text-gray-400">to</span>
          <select name="to" defaultValue={to ?? ""}
            className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 bg-white">
            <option value="">To</option>
            {[...allYears].reverse().map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <button type="submit"
            className="rounded px-2 py-1 bg-gray-800 text-white hover:bg-gray-700">
            Apply
          </button>
          {(from || to) && (
            <a href={buildUrl(cp, { from: undefined, to: undefined })}
              className="rounded px-2 py-1 bg-gray-100 text-gray-600 hover:bg-gray-200">
              Clear
            </a>
          )}
        </form>
      )}

      {/* Party top donors */}
      {pol.party && topDonors.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">
              Top donors to{" "}
              <a href={`/party/${pol.party.id}`} className="text-blue-600 hover:underline">
                {pol.party.abbreviation || pol.party.name}
              </a>{" "}
              <span className="font-normal text-gray-400 text-sm">
                (top 10)
              </span>
            </h2>
            <a href={`/party/${pol.party.id}`} className="text-xs text-blue-600 hover:underline">
              Full party profile →
            </a>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                  <th className="py-2 pr-4 text-gray-500">#</th>
                  <SortTh label="Donor"    sortKey="donor"    current={ptdSort} href={buildUrl(cp, { ptd: "donor" })} />
                  <SortTh label="Industry" sortKey="industry" current={ptdSort} href={buildUrl(cp, { ptd: "industry" })} />
                  <SortTh label="Total donated" sortKey="total" current={ptdSort} href={buildUrl(cp, { ptd: "total" })} right />
                </tr>
              </thead>
              <tbody>
                {topDonors.map((d, i) => (
                  <tr key={d.donor.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 pr-4 text-gray-400 tabular-nums">{i + 1}</td>
                    <td className="py-2 pr-4">
                      <a href={`/donor/${d.donor.id}`} className="text-blue-600 hover:underline">
                        {d.donor.name}
                      </a>
                    </td>
                    <td className="py-2 pr-4 text-xs text-gray-500">{d.donor.industry_label || "—"}</td>
                    <td className="py-2 text-right tabular-nums">
                      ${d.total.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Register of Interests */}
      <section>
        <h2 className="mb-3 font-semibold text-gray-900">
          Register of Interests — gifts & travel{" "}
          <span className="font-normal text-gray-400 text-sm">
            ({interests.length} of {filteredInterests.length}{(from || to) ? ` filtered` : ""})
          </span>
        </h2>
        {pol.interests.length === 0 ? (
          <p className="text-sm text-gray-400">No declared interests on record.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                    <SortTh label="Description" sortKey="description" current={intSort} href={buildUrl(cp, { int: "description" })} />
                    <SortTh label="Provider"    sortKey="provider"    current={intSort} href={buildUrl(cp, { int: "provider" })} />
                    <SortTh label="Received"    sortKey="received"    current={intSort} href={buildUrl(cp, { int: "received" })} />
                    <SortTh label="Declared"    sortKey="declared"    current={intSort} href={buildUrl(cp, { int: "declared" })} />
                    <SortTh label="Days late"   sortKey="days_late"   current={intSort} href={buildUrl(cp, { int: "days_late" })} right />
                    <th className="py-2 text-gray-500 uppercase tracking-wide text-xs">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {interests.map((i) => (
                    <tr key={i.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 pr-4 max-w-xs text-xs leading-snug">{i.description || "—"}</td>
                      <td className="py-2 pr-4 text-xs">
                        {i.donor ? (
                          <a href={`/donor/${i.donor.id}`} className="text-blue-600 hover:underline">
                            {i.donor.name}
                          </a>
                        ) : "—"}
                      </td>
                      <td className="py-2 pr-4 text-xs tabular-nums">{i.date_received || "—"}</td>
                      <td className="py-2 pr-4 text-xs tabular-nums">{i.date_declared || "—"}</td>
                      <td className="py-2 pr-4 text-xs text-right">
                        {i.days_late != null ? (
                          <span className={i.days_late > 0 ? "text-red-600 font-medium" : "text-gray-500"}>
                            {i.days_late > 0 ? `+${i.days_late}` : i.days_late}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="py-2">
                        {i.source_url ? (
                          <a href={i.source_url} target="_blank" rel="noopener noreferrer"
                             className="text-xs text-blue-500 hover:underline">↗</a>
                        ) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {filteredInterests.length > DEFAULT_LIMIT && (
              <p className="mt-2 text-xs">
                {intl === "all" ? (
                  <a href={buildUrl(cp, { intl: undefined })} className="text-blue-600 hover:underline">
                    Show top {DEFAULT_LIMIT}
                  </a>
                ) : (
                  <a href={buildUrl(cp, { intl: "all" })} className="text-blue-600 hover:underline">
                    Show all {filteredInterests.length}
                  </a>
                )}
              </p>
            )}
          </>
        )}
      </section>

      {/* Direct donations */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">
            Direct donations received{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({directDons.length} of {filteredDirectDons.length}{(from || to) ? ` filtered` : ""})
            </span>
          </h2>
          {pol.direct_donations.length > 0 && (
            <a
              href={`http://localhost:8000/api/v1/politicians/${id}?format=csv`}
              className="text-xs text-blue-600 hover:underline"
            >
              Download CSV
            </a>
          )}
        </div>
        {pol.direct_donations.length === 0 ? (
          <p className="text-sm text-gray-400">
            No direct donations on record. Most donations flow via party — see party profile above.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                    <SortTh label="Year"     sortKey="year"     current={ddSort} href={buildUrl(cp, { dd: "year" })} />
                    <SortTh label="Amount"   sortKey="amount"   current={ddSort} href={buildUrl(cp, { dd: "amount" })} right />
                    <SortTh label="Donor"    sortKey="donor"    current={ddSort} href={buildUrl(cp, { dd: "donor" })} />
                    <SortTh label="Industry" sortKey="industry" current={ddSort} href={buildUrl(cp, { dd: "industry" })} />
                    <th className="py-2 text-gray-500 uppercase tracking-wide text-xs">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {directDons.map((d) => (
                    <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 pr-4">{d.financial_year}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">
                        ${d.amount.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                      </td>
                      <td className="py-2 pr-4">
                        {d.donor ? (
                          <a href={`/donor/${d.donor.id}`} className="text-blue-600 hover:underline">
                            {d.donor.name}
                          </a>
                        ) : "—"}
                      </td>
                      <td className="py-2 pr-4 text-gray-500 text-xs">{d.donor?.industry_label || "—"}</td>
                      <td className="py-2">
                        {d.source_url ? (
                          <a href={d.source_url} target="_blank" rel="noopener noreferrer"
                             className="text-xs text-blue-500 hover:underline">AEC ↗</a>
                        ) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {filteredDirectDons.length > DEFAULT_LIMIT && (
              <p className="mt-2 text-xs">
                {ddl === "all" ? (
                  <a href={buildUrl(cp, { ddl: undefined })} className="text-blue-600 hover:underline">
                    Show top {DEFAULT_LIMIT}
                  </a>
                ) : (
                  <a href={buildUrl(cp, { ddl: "all" })} className="text-blue-600 hover:underline">
                    Show all {filteredDirectDons.length}
                  </a>
                )}
              </p>
            )}
          </>
        )}
      </section>

      {/* Via party branch donations */}
      {pol.via_party_donations.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Donations via named party branch{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({viaBranchDons.length} of {filteredViaBranchDons.length}{(from || to) ? ` filtered` : ""})
            </span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                  <SortTh label="Year"         sortKey="year"   current={vpbSort} href={buildUrl(cp, { vpb: "year" })} />
                  <SortTh label="Amount"        sortKey="amount" current={vpbSort} href={buildUrl(cp, { vpb: "amount" })} right />
                  <SortTh label="Donor"         sortKey="donor"  current={vpbSort} href={buildUrl(cp, { vpb: "donor" })} />
                  <SortTh label="Party branch"  sortKey="branch" current={vpbSort} href={buildUrl(cp, { vpb: "branch" })} />
                  <th className="py-2 text-gray-500 uppercase tracking-wide text-xs">Source</th>
                </tr>
              </thead>
              <tbody>
                {viaBranchDons.map((d) => (
                  <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 pr-4">{d.financial_year}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      ${d.amount.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-2 pr-4">
                      {d.donor ? (
                        <a href={`/donor/${d.donor.id}`} className="text-blue-600 hover:underline">
                          {d.donor.name}
                        </a>
                      ) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-xs text-gray-500">
                      <a href={`/party/${d.party_id}`} className="hover:underline">{d.party_name}</a>
                    </td>
                    <td className="py-2">
                      {d.source_url ? (
                        <a href={d.source_url} target="_blank" rel="noopener noreferrer"
                           className="text-xs text-blue-500 hover:underline">AEC ↗</a>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredViaBranchDons.length > DEFAULT_LIMIT && (
            <p className="mt-2 text-xs">
              {vpbl === "all" ? (
                <a href={buildUrl(cp, { vpbl: undefined })} className="text-blue-600 hover:underline">
                  Show top {DEFAULT_LIMIT}
                </a>
              ) : (
                <a href={buildUrl(cp, { vpbl: "all" })} className="text-blue-600 hover:underline">
                  Show all {filteredViaBranchDons.length}
                </a>
              )}
            </p>
          )}
        </section>
      )}

      {/* Donations made as a donor */}
      {pol.as_donor_donations.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Donations made{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({asDonorDons.length} of {filteredAsDonorDons.length}{(from || to) ? ` filtered` : ""})
            </span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                  <SortTh label="Year"       sortKey="year"      current={dmSort} href={buildUrl(cp, { dm: "year" })} />
                  <SortTh label="Amount"     sortKey="amount"    current={dmSort} href={buildUrl(cp, { dm: "amount" })} right />
                  <SortTh label="Donor name" sortKey="donor"     current={dmSort} href={buildUrl(cp, { dm: "donor" })} />
                  <SortTh label="Recipient"  sortKey="recipient" current={dmSort} href={buildUrl(cp, { dm: "recipient" })} />
                  <th className="py-2 text-gray-500 uppercase tracking-wide text-xs">Source</th>
                </tr>
              </thead>
              <tbody>
                {asDonorDons.map((d) => (
                  <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 pr-4">{d.financial_year}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      ${d.amount.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-2 pr-4 text-xs text-gray-500">{d.donor_name}</td>
                    <td className="py-2 pr-4 text-xs">
                      {d.recipient_party_id ? (
                        <a href={`/party/${d.recipient_party_id}`} className="text-blue-600 hover:underline">
                          {d.recipient_party_name}
                        </a>
                      ) : d.recipient_politician_id ? (
                        <a href={`/politician/${d.recipient_politician_id}`} className="text-blue-600 hover:underline">
                          {d.recipient_politician_name}
                        </a>
                      ) : "—"}
                    </td>
                    <td className="py-2">
                      {d.source_url ? (
                        <a href={d.source_url} target="_blank" rel="noopener noreferrer"
                           className="text-xs text-blue-500 hover:underline">AEC ↗</a>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredAsDonorDons.length > DEFAULT_LIMIT && (
            <p className="mt-2 text-xs">
              {dml === "all" ? (
                <a href={buildUrl(cp, { dml: undefined })} className="text-blue-600 hover:underline">
                  Show top {DEFAULT_LIMIT}
                </a>
              ) : (
                <a href={buildUrl(cp, { dml: "all" })} className="text-blue-600 hover:underline">
                  Show all {filteredAsDonorDons.length}
                </a>
              )}
            </p>
          )}
        </section>
      )}

      {/* Voting record */}
      <section>
        <div className="mb-2 flex flex-wrap items-center gap-4">
          <h2 className="font-semibold text-gray-900">
            Voting record{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({visibleVotes.length} of {filteredVotes.length}{(selectedParliament || selectedIssue || from || to) ? ` filtered` : ""})
            </span>
          </h2>
        </div>
        {parliamentsWithVotes.length > 1 && (
          <div className="mb-3 flex flex-wrap gap-1 text-xs">
            <span className="py-1 text-gray-400 mr-1">Parliament</span>
            <a
              href={buildUrl(cp, { parliament: undefined })}
              className={`rounded px-2 py-1 ${!selectedParliament ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
            >
              All
            </a>
            {parliamentsWithVotes.map((p) => (
              <a
                key={p}
                href={buildUrl(cp, { parliament: String(p) })}
                className={`rounded px-2 py-1 ${selectedParliament === p ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
              >
                {p}th
              </a>
            ))}
          </div>
        )}
        {allIssueTags.length > 0 && (
          <form method="GET" className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            {Object.entries(cp).filter(([k, v]) => v && k !== "issue").map(([k, v]) => (
              <input key={k} type="hidden" name={k} value={v} />
            ))}
            <span className="text-gray-400">Issue</span>
            <select name="issue" defaultValue={selectedIssue ?? ""}
              className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 bg-white">
              <option value="">All</option>
              {allIssueTags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
            </select>
            <button type="submit"
              className="rounded px-2 py-1 bg-gray-800 text-white hover:bg-gray-700">
              Apply
            </button>
            {selectedIssue && (
              <a href={buildUrl(cp, { issue: undefined })}
                className="rounded px-2 py-1 bg-gray-100 text-gray-600 hover:bg-gray-200">
                Clear
              </a>
            )}
          </form>
        )}
        {pol.votes.length === 0 ? (
          <p className="text-sm text-gray-400">No voting record on file.</p>
        ) : filteredVotes.length === 0 ? (
          <p className="text-sm text-gray-400">No votes found for the {selectedParliament}th Parliament.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                  <SortTh label="Date"         sortKey="date"  current={voteSort} href={buildUrl(cp, { sort: "date" })} />
                  <SortTh label="Vote"         sortKey="vote"  current={voteSort} href={buildUrl(cp, { sort: "vote" })} />
                  <th className="py-2 pr-4 text-gray-500">Bill / Motion</th>
                  <SortTh label="Issues"       sortKey="issue" current={voteSort} href={buildUrl(cp, { sort: "issue" })} />
                </tr>
              </thead>
              <tbody>
                {visibleVotes.map((v) => {
                  const link = tvfyUrl(v);
                  return (
                    <tr key={v.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 pr-4 tabular-nums text-xs">{v.vote_date || "—"}</td>
                      <td className="py-2 pr-4">
                        <span className={
                          v.vote_direction === "aye"
                            ? "text-green-700 font-medium"
                            : v.vote_direction === "no"
                            ? "text-red-600 font-medium"
                            : "text-gray-500"
                        }>
                          {v.vote_direction}
                        </span>
                      </td>
                      <td className="py-2 pr-4 max-w-sm text-xs leading-snug">
                        {link ? (
                          <a href={link} target="_blank" rel="noopener noreferrer"
                             className="text-blue-600 hover:underline">
                            {v.bill_title}
                          </a>
                        ) : v.bill_title}
                      </td>
                      <td className="py-2 text-xs max-w-xs">
                        {v.policy_positions?.length
                          ? policyStance(v.policy_positions, v.vote_direction)
                          : v.issue_tags?.slice(0, 3).join(", ")
                            ? <span className="text-gray-400">{v.issue_tags.slice(0, 3).join(", ")}</span>
                            : <span className="text-gray-300">—</span>
                        }
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {filteredVotes.length > DEFAULT_LIMIT && (
          <p className="mt-2 text-xs">
            {vl === "all" ? (
              <a href={buildUrl(cp, { vl: undefined })} className="text-blue-600 hover:underline">
                Show top {DEFAULT_LIMIT}
              </a>
            ) : (
              <a href={buildUrl(cp, { vl: "all" })} className="text-blue-600 hover:underline">
                Show all {filteredVotes.length}
              </a>
            )}
          </p>
        )}
        {filteredVotes.length > 0 && (
          <p className="mt-2 text-xs text-gray-400">
            Voting data sourced from{" "}
            <a href="https://theyvoteforyou.org.au" target="_blank" rel="noopener noreferrer"
               className="underline">They Vote For You</a>.
          </p>
        )}
      </section>
    </div>
  );
}
