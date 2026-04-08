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

const DEFAULT_LIMIT = 10;

export default async function DonorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    sort?: string; psort?: string; gsort?: string; from?: string; to?: string;
    gl?: string; pl?: string; dl?: string;
  }>;
}) {
  const { id } = await params;
  const { sort, psort, gsort, from, to, gl, pl, dl } = await searchParams;

  const donationSort: DonationSort =
    sort === "recipient" || sort === "year" || sort === "type" ? sort : "amount";
  const partySort: PartySort = psort === "party" ? "party" : "total";
  const giftSort: GiftSort =
    gsort === "politician" || gsort === "value" || gsort === "received" ? gsort : "declared";

  const donor = await fetchDonor(id);
  if (!donor) notFound();

  const cp = { sort, psort, gsort, from, to, gl, pl, dl }; // current params

  const giftLimit     = gl === "all" ? Infinity : DEFAULT_LIMIT;
  const partyLimit    = pl === "all" ? Infinity : DEFAULT_LIMIT;
  const donationLimit = dl === "all" ? Infinity : DEFAULT_LIMIT;

  // Current financial year (July–June), e.g. "2025-26"
  const now = new Date();
  const fyStartYear = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
  const currentFY = `${fyStartYear}-${String(fyStartYear + 1).slice(2)}`;

  const allFinancialYears = [...new Set(
    [...donor.donations.map((d) => d.financial_year).filter((y): y is string => !!y), currentFY]
  )].sort();

  // Convert financial year "YYYY-YY" to start/end ISO dates for gifts filtering
  const fyStart = from ? `${from.split("-")[0]}-07-01` : null;
  const fyEnd   = to   ? `${parseInt(to.split("-")[0]) + 1}-06-30` : null;

  const filteredDonations = donor.donations
    .filter((d) => !from || !d.financial_year || d.financial_year >= from)
    .filter((d) => !to   || !d.financial_year || d.financial_year <= to);

  // Re-aggregate donations by party from filtered set
  const byPartyMap = new Map<number, PartyTotalRow>();
  for (const d of filteredDonations) {
    if (!d.party) continue;
    const entry = byPartyMap.get(d.party.id) ?? { party: d.party, total: 0 };
    entry.total += d.amount;
    byPartyMap.set(d.party.id, entry);
  }
  const filteredByParty = (from || to)
    ? [...byPartyMap.values()]
    : donor.donations_by_party;

  const filteredGifts = donor.interests
    .filter((g) => !fyStart || !g.date_declared || g.date_declared >= fyStart)
    .filter((g) => !fyEnd   || !g.date_declared || g.date_declared <= fyEnd);

  const filteredTotalDonated = filteredDonations.reduce((sum, d) => sum + d.amount, 0);

  const sortedDonations = sortDonations(filteredDonations, donationSort);
  const sortedByParty   = sortByParty(filteredByParty, partySort);
  const sortedGifts     = sortGifts(filteredGifts, giftSort);

  const visibleGifts     = sortedGifts.slice(0, giftLimit);
  const visibleByParty   = sortedByParty.slice(0, partyLimit);
  const visibleDonations = sortedDonations.slice(0, donationLimit);

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
                ${((from || to) ? filteredTotalDonated : donor.total_donated)
                  .toLocaleString("en-AU", { maximumFractionDigits: 0 })}
              </span>
              {(from || to) && (
                <span className="ml-2 text-sm font-normal text-gray-400">
                  (${donor.total_donated.toLocaleString("en-AU", { maximumFractionDigits: 0 })} all time)
                </span>
              )}
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

      {/* Year filter */}
      {allFinancialYears.length > 1 && (
        <form method="GET" className="flex flex-wrap items-center gap-2 text-xs">
          {Object.entries(cp).filter(([k, v]) => v && k !== "from" && k !== "to").map(([k, v]) => (
            <input key={k} type="hidden" name={k} value={v} />
          ))}
          <span className="text-gray-400">Filter by year</span>
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

      {/* Gifts & travel — Register of Interests */}
      {sortedGifts.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Gifts & travel declared{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({visibleGifts.length} of {filteredGifts.length}{(from || to) ? ` filtered` : ""})
            </span>
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
                {visibleGifts.map((g) => (
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
          {filteredGifts.length > DEFAULT_LIMIT && (
            <p className="mt-2 text-xs">
              {gl === "all" ? (
                <a href={buildUrl(cp, { gl: undefined })} className="text-blue-600 hover:underline">
                  Show top {DEFAULT_LIMIT}
                </a>
              ) : (
                <a href={buildUrl(cp, { gl: "all" })} className="text-blue-600 hover:underline">
                  Show all {filteredGifts.length}
                </a>
              )}
            </p>
          )}
        </section>
      )}

      {/* By party */}
      {sortedByParty.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Donations by party{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({visibleByParty.length} of {filteredByParty.length}{(from || to) ? ` filtered` : ""})
            </span>
          </h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                <SortTh label="Party" sortKey="party" current={partySort} href={buildUrl(cp, { psort: "party" })} />
                <SortTh label="Total" sortKey="total" current={partySort} href={buildUrl(cp, { psort: "total" })} right />
              </tr>
            </thead>
            <tbody>
              {visibleByParty.map((r, i) => (
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
          {filteredByParty.length > DEFAULT_LIMIT && (
            <p className="mt-2 text-xs">
              {pl === "all" ? (
                <a href={buildUrl(cp, { pl: undefined })} className="text-blue-600 hover:underline">
                  Show top {DEFAULT_LIMIT}
                </a>
              ) : (
                <a href={buildUrl(cp, { pl: "all" })} className="text-blue-600 hover:underline">
                  Show all {filteredByParty.length}
                </a>
              )}
            </p>
          )}
        </section>
      )}

      {/* All donations */}
      {donor.donations.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">
              All donations{" "}
              <span className="text-gray-400 font-normal text-sm">
                ({visibleDonations.length} of {filteredDonations.length}{(from || to) ? ` filtered` : ""})
              </span>
            </h2>
            <a
              href={`http://localhost:8000/api/v1/donors/${id}?format=csv`}
              className="text-xs text-blue-600 hover:underline"
            >
              Download CSV
            </a>
          </div>
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
                {visibleDonations.map((d) => (
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
          {filteredDonations.length > DEFAULT_LIMIT && (
            <p className="mt-2 text-xs">
              {dl === "all" ? (
                <a href={buildUrl(cp, { dl: undefined })} className="text-blue-600 hover:underline">
                  Show top {DEFAULT_LIMIT}
                </a>
              ) : (
                <a href={buildUrl(cp, { dl: "all" })} className="text-blue-600 hover:underline">
                  Show all {filteredDonations.length}
                </a>
              )}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
