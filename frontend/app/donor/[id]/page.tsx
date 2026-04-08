import { notFound } from "next/navigation";
import { fetchDonor, DonationByPartyRow, PartyTotalRow, DonorInterestRow } from "../../lib/api";

// ── Sort types ──────────────────────────────────────────────────────────────

type DonationSort = "amount" | "recipient" | "year" | "type";
type PartySort    = "party"  | "total";
type GiftSort     = "politician" | "value" | "received" | "declared";

function sortDonations(donations: DonationByPartyRow[], sort: DonationSort): DonationByPartyRow[] {
  return [...donations].sort((a, b) => {
    if (sort === "amount") return b.amount - a.amount;
    if (sort === "year")   return (b.financial_year ?? "").localeCompare(a.financial_year ?? "");
    if (sort === "type")   return (a.donation_type ?? "").localeCompare(b.donation_type ?? "");
    const nameA = a.party?.name ?? a.politician_name ?? "";
    const nameB = b.party?.name ?? b.politician_name ?? "";
    return nameA.localeCompare(nameB);
  });
}

function sortByParty(rows: PartyTotalRow[], sort: PartySort): PartyTotalRow[] {
  return [...rows].sort((a, b) =>
    sort === "party" ? a.party.name.localeCompare(b.party.name) : b.total - a.total
  );
}

function sortGifts(rows: DonorInterestRow[], sort: GiftSort): DonorInterestRow[] {
  return [...rows].sort((a, b) => {
    if (sort === "politician") return (a.politician?.name ?? "").localeCompare(b.politician?.name ?? "");
    if (sort === "value")      return (b.value_approx ?? 0) - (a.value_approx ?? 0);
    if (sort === "received")   return (b.date_received ?? "").localeCompare(a.date_received ?? "");
    return (b.date_declared ?? "").localeCompare(a.date_declared ?? ""); // declared (default)
  });
}

// ── URL helper ───────────────────────────────────────────────────────────────

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

// ── Sort header helper ───────────────────────────────────────────────────────

function SortTh({
  label,
  sortKey,
  current,
  href,
  right,
  className,
}: {
  label: string;
  sortKey: string;
  current: string;
  href: string;
  right?: boolean;
  className?: string;
}) {
  const active = current === sortKey;
  return (
    <th className={`py-2 pr-4 ${right ? "text-right" : ""} ${className ?? ""}`}>
      <a
        href={href}
        className={active ? "font-semibold text-gray-800" : "text-gray-500 hover:text-gray-700"}
      >
        {label}{active ? " ↓" : ""}
      </a>
    </th>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default async function DonorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ sort?: string; psort?: string; gsort?: string; from?: string; to?: string }>;
}) {
  const { id } = await params;
  const { sort, psort, gsort, from, to } = await searchParams;

  const donationSort: DonationSort =
    sort === "recipient" || sort === "year" || sort === "type" ? sort : "amount";
  const partySort: PartySort = psort === "party" ? "party" : "total";
  const giftSort: GiftSort =
    gsort === "politician" || gsort === "value" || gsort === "received" ? gsort : "declared";

  const donor = await fetchDonor(id);
  if (!donor) notFound();

  const cp = { sort, psort, gsort, from, to }; // current params

  const allFinancialYears = [...new Set(
    donor.donations.map((d) => d.financial_year).filter((y): y is string => !!y)
  )].sort();

  const filteredDonations = donor.donations
    .filter((d) => !from || !d.financial_year || d.financial_year >= from)
    .filter((d) => !to   || !d.financial_year || d.financial_year <= to);

  const sortedDonations = sortDonations(filteredDonations, donationSort);
  const sortedByParty   = sortByParty(donor.donations_by_party, partySort);
  const sortedGifts     = sortGifts(donor.interests, giftSort);

  return (
    <div className="space-y-8">
      {/* Identity */}
      <div>
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-bold">{donor.name}</h1>
          {donor.needs_review && (
            <span className="shrink-0 rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
              Unresolved
            </span>
          )}
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
          {donor.entity_type && (
            <>
              <dt className="text-gray-500">Type</dt>
              <dd>{donor.entity_type}</dd>
            </>
          )}
          {donor.industry_label && (
            <>
              <dt className="text-gray-500">Industry</dt>
              <dd>{donor.industry_label}</dd>
            </>
          )}
          {donor.abn && (
            <>
              <dt className="text-gray-500">ABN</dt>
              <dd>{donor.abn}</dd>
            </>
          )}
          {donor.anzsic_code && (
            <>
              <dt className="text-gray-500">ANZSIC</dt>
              <dd>{donor.anzsic_code}</dd>
            </>
          )}
          {donor.controlling_person && (
            <>
              <dt className="text-gray-500">Directors</dt>
              <dd>{donor.controlling_person}</dd>
            </>
          )}
        </dl>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1">
          {donor.total_donated > 0 && (
            <p className="text-lg font-semibold">
              Total donated:{" "}
              <span className="text-gray-700">
                ${donor.total_donated.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
              </span>
            </p>
          )}
          {donor.total_gifted > 0 && (
            <p className="text-lg font-semibold">
              Total gifted:{" "}
              <span className="text-gray-700">
                ${donor.total_gifted.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
              </span>
              <span className="ml-1 text-sm font-normal text-gray-400">(approx)</span>
            </p>
          )}
        </div>
      </div>

      {/* Gifts & travel — Register of Interests */}
      {sortedGifts.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Gifts & travel declared{" "}
            <span className="font-normal text-gray-400 text-sm">({sortedGifts.length})</span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                  <SortTh label="Politician"  sortKey="politician" current={giftSort} href={buildUrl(cp, { gsort: "politician" })} />
                  <th className="py-2 pr-4 text-gray-500 uppercase tracking-wide text-xs">Description</th>
                  <SortTh label="Value"       sortKey="value"       current={giftSort} href={buildUrl(cp, { gsort: "value" })} right />
                  <SortTh label="Received"    sortKey="received"    current={giftSort} href={buildUrl(cp, { gsort: "received" })} />
                  <SortTh label="Declared"    sortKey="declared"    current={giftSort} href={buildUrl(cp, { gsort: "declared" })} />
                  <th className="py-2 text-gray-500 uppercase tracking-wide text-xs">Source</th>
                </tr>
              </thead>
              <tbody>
                {sortedGifts.map((g) => (
                  <tr key={g.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 pr-4 text-xs">
                      {g.politician ? (
                        <a href={`/politician/${g.politician.id}`} className="text-blue-600 hover:underline">
                          {g.politician.name}
                        </a>
                      ) : "—"}
                    </td>
                    <td className="py-2 pr-4 max-w-xs text-xs leading-snug">{g.description || "—"}</td>
                    <td className="py-2 pr-4 text-right tabular-nums text-xs">
                      {g.value_approx != null
                        ? `$${g.value_approx.toLocaleString("en-AU", { maximumFractionDigits: 0 })}`
                        : "—"}
                    </td>
                    <td className="py-2 pr-4 tabular-nums text-xs">{g.date_received || "—"}</td>
                    <td className="py-2 pr-4 tabular-nums text-xs">{g.date_declared || "—"}</td>
                    <td className="py-2">
                      {g.source_url ? (
                        <a href={g.source_url} target="_blank" rel="noopener noreferrer"
                           className="text-xs text-blue-500 hover:underline">↗</a>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* By party */}
      {sortedByParty.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Donations by party</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                <SortTh label="Party" sortKey="party" current={partySort} href={buildUrl(cp, { psort: "party" })} />
                <SortTh label="Total" sortKey="total" current={partySort} href={buildUrl(cp, { psort: "total" })} right />
              </tr>
            </thead>
            <tbody>
              {sortedByParty.map((r, i) => (
                <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-2 pr-4">
                    <a href={`/party/${r.party.id}`} className="text-blue-600 hover:underline">
                      {r.party.name}
                    </a>
                    {r.party.abbreviation && (
                      <span className="ml-1 text-gray-400 text-xs">({r.party.abbreviation})</span>
                    )}
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    ${r.total.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* All donations */}
      {donor.donations.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">
              All donations{" "}
              <span className="text-gray-400 font-normal text-sm">
                ({filteredDonations.length}{(from || to) ? ` of ${donor.donations.length} filtered` : ""})
              </span>
            </h2>
            <a
              href={`http://localhost:8000/api/v1/donors/${id}?format=csv`}
              className="text-xs text-blue-600 hover:underline"
            >
              Download CSV
            </a>
          </div>
          {allFinancialYears.length > 1 && (
            <form method="GET" className="mb-3 flex flex-wrap items-center gap-2 text-xs">
              {Object.entries(cp).filter(([k, v]) => v && k !== "from" && k !== "to").map(([k, v]) => (
                <input key={k} type="hidden" name={k} value={v} />
              ))}
              <span className="text-gray-400">Year</span>
              <select name="from" defaultValue={from ?? ""}
                className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 bg-white">
                <option value="">From</option>
                {allFinancialYears.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <span className="text-gray-400">to</span>
              <select name="to" defaultValue={to ?? ""}
                className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 bg-white">
                <option value="">To</option>
                {[...allFinancialYears].reverse().map((y) => <option key={y} value={y}>{y}</option>)}
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                  <SortTh label="Year"      sortKey="year"      current={donationSort} href={buildUrl(cp, { sort: "year" })} />
                  <SortTh label="Amount"    sortKey="amount"    current={donationSort} href={buildUrl(cp, { sort: "amount" })} right />
                  <SortTh label="Recipient" sortKey="recipient" current={donationSort} href={buildUrl(cp, { sort: "recipient" })} />
                  <SortTh label="Type"      sortKey="type"      current={donationSort} href={buildUrl(cp, { sort: "type" })} />
                  <th className="py-2 text-xs text-gray-500 uppercase tracking-wide">Source</th>
                </tr>
              </thead>
              <tbody>
                {sortedDonations.map((d) => (
                  <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 pr-4 tabular-nums">{d.financial_year}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      ${d.amount.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-2 pr-4">
                      {d.party ? (
                        <a href={`/party/${d.party.id}`} className="text-blue-600 hover:underline">
                          {d.party.abbreviation || d.party.name}
                        </a>
                      ) : d.politician_name ? (
                        <a href={`/politician/${d.politician_id}`} className="text-blue-600 hover:underline">
                          {d.politician_name}
                        </a>
                      ) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-gray-500 text-xs">{d.donation_type || "—"}</td>
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
        </section>
      )}
    </div>
  );
}
