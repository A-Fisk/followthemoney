import { notFound } from "next/navigation";
import { fetchParty, PartyDetail, PartyFinancialsRow, TopDonorRow } from "../../lib/api";

// ── Sort types ──────────────────────────────────────────────────────────────

type YrSort  = "year"  | "total";
type IndSort = "industry" | "total";
type DonSort = "donor" | "industry" | "total";
type ExpSort = "year"  | "category" | "amount";

function sortByYear(rows: PartyDetail["donations_by_year"], s: YrSort) {
  return [...rows].sort((a, b) =>
    s === "total" ? b.total - a.total
                  : (b.financial_year ?? "").localeCompare(a.financial_year ?? "")
  );
}

function sortByInd(rows: PartyDetail["industry_breakdown"], s: IndSort) {
  return [...rows].sort((a, b) =>
    s === "industry" ? (a.industry_label ?? "").localeCompare(b.industry_label ?? "")
                     : b.total - a.total
  );
}

function sortTopDonors(rows: TopDonorRow[], s: DonSort) {
  return [...rows].sort((a, b) => {
    if (s === "donor")    return a.donor.name.localeCompare(b.donor.name);
    if (s === "industry") return (a.donor.industry_label ?? "").localeCompare(b.donor.industry_label ?? "");
    return b.total - a.total;
  });
}

function sortExpenditure(rows: PartyDetail["expenditure"], s: ExpSort) {
  return [...rows].sort((a, b) => {
    if (s === "category") return (a.category ?? "").localeCompare(b.category ?? "");
    if (s === "amount")   return b.amount - a.amount;
    return (b.financial_year ?? "").localeCompare(a.financial_year ?? "");
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

// ── Page ─────────────────────────────────────────────────────────────────────

export default async function PartyPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ yrs?: string; ind?: string; don?: string; exp?: string; from?: string; to?: string }>;
}) {
  const { id } = await params;
  const { yrs, ind, don, exp, from, to } = await searchParams;

  const yrSort:  YrSort  = yrs === "total"    ? "total"    : "year";
  const indSort: IndSort = ind === "industry" ? "industry" : "total";
  const donSort: DonSort = don === "donor" || don === "industry" ? don : "total";
  const expSort: ExpSort = exp === "category" || exp === "amount" ? exp : "year";

  const party = await fetchParty(id);
  if (!party) notFound();

  const cp = { yrs, ind, don, exp, from, to }; // current params for URL building

  // Current financial year always available in "to" dropdown
  const now = new Date();
  const fyStartYear = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
  const currentFY = `${fyStartYear}-${String(fyStartYear + 1).slice(2)}`;

  const allFinancialYears = [...new Set(
    [...party.donations_by_year.map((r) => r.financial_year), currentFY]
  )].sort();

  const filteredByYear = party.donations_by_year
    .filter((r) => !from || r.financial_year >= from)
    .filter((r) => !to   || r.financial_year <= to);

  const filteredExpenditure = party.expenditure
    .filter((r) => !from || r.financial_year >= from)
    .filter((r) => !to   || r.financial_year <= to);

  const filteredTotal = filteredByYear.reduce((sum, r) => sum + r.total, 0);

  const byYear    = sortByYear(filteredByYear, yrSort);
  const byInd     = sortByInd(party.industry_breakdown, indSort);
  const topDonors = sortTopDonors(party.top_donors, donSort);
  const expRows   = sortExpenditure(filteredExpenditure, expSort);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">
          {party.name}
          {party.abbreviation && (
            <span className="ml-2 text-lg font-normal text-gray-400">
              ({party.abbreviation})
            </span>
          )}
        </h1>
        <p className="mt-1 text-lg font-semibold text-gray-700">
          Total donations:{" "}
          ${((from || to) ? filteredTotal : party.total_donations)
            .toLocaleString("en-AU", { maximumFractionDigits: 0 })}
          {(from || to) && (
            <span className="ml-2 text-sm font-normal text-gray-400">
              (${party.total_donations.toLocaleString("en-AU", { maximumFractionDigits: 0 })} all time)
            </span>
          )}
        </p>
        <a
          href={`http://localhost:8000/api/v1/parties/${id}?format=csv`}
          className="mt-1 inline-block text-xs text-blue-600 hover:underline"
        >
          Download donations by year (CSV)
        </a>
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

      {/* Donations by year */}
      {byYear.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Donations by year</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                <SortTh label="Financial year" sortKey="year"  current={yrSort} href={buildUrl(cp, { yrs: "year" })} />
                <SortTh label="Total"          sortKey="total" current={yrSort} href={buildUrl(cp, { yrs: "total" })} right />
              </tr>
            </thead>
            <tbody>
              {byYear.map((r) => (
                <tr key={r.financial_year} className="border-b border-gray-100">
                  <td className="py-2 pr-4">{r.financial_year}</td>
                  <td className="py-2 text-right tabular-nums">
                    ${r.total.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Industry breakdown */}
      {byInd.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Donations by industry{" "}
            {(from || to) && <span className="font-normal text-gray-400 text-sm">(all time)</span>}
          </h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                <SortTh label="Industry" sortKey="industry" current={indSort} href={buildUrl(cp, { ind: "industry" })} />
                <SortTh label="Total"    sortKey="total"    current={indSort} href={buildUrl(cp, { ind: "total" })} right />
              </tr>
            </thead>
            <tbody>
              {byInd.slice(0, 20).map((r) => (
                <tr key={r.industry_label} className="border-b border-gray-100">
                  <td className="py-2 pr-4">{r.industry_label}</td>
                  <td className="py-2 text-right tabular-nums">
                    ${r.total.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Top donors */}
      {topDonors.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Top donors{" "}
            {(from || to) && <span className="font-normal text-gray-400 text-sm">(all time)</span>}
          </h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                <SortTh label="Donor"    sortKey="donor"    current={donSort} href={buildUrl(cp, { don: "donor" })} />
                <SortTh label="Industry" sortKey="industry" current={donSort} href={buildUrl(cp, { don: "industry" })} />
                <SortTh label="Total"    sortKey="total"    current={donSort} href={buildUrl(cp, { don: "total" })} right />
              </tr>
            </thead>
            <tbody>
              {topDonors.map((r) => (
                <tr key={r.donor.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-2 pr-4">
                    <a href={`/donor/${r.donor.id}`} className="text-blue-600 hover:underline">
                      {r.donor.name}
                    </a>
                    {r.donor.needs_review && (
                      <span className="ml-1 text-xs text-yellow-600">⚠ unresolved</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-gray-500 text-xs">
                    {r.donor.industry_label || "—"}
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

      {/* Expenditure */}
      {expRows.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Expenditure</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                <SortTh label="Year"     sortKey="year"     current={expSort} href={buildUrl(cp, { exp: "year" })} />
                <SortTh label="Category" sortKey="category" current={expSort} href={buildUrl(cp, { exp: "category" })} />
                <SortTh label="Amount"   sortKey="amount"   current={expSort} href={buildUrl(cp, { exp: "amount" })} right />
              </tr>
            </thead>
            <tbody>
              {expRows.map((r, i) => (
                <tr key={i} className="border-b border-gray-100">
                  <td className="py-2 pr-4">{r.financial_year}</td>
                  <td className="py-2 pr-4 text-gray-600">{r.category}</td>
                  <td className="py-2 text-right tabular-nums">
                    ${r.amount.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Financial summary (Party Returns totals) */}
      {party.financials.length > 0 && (
        <section>
          <h2 className="mb-1 font-semibold text-gray-900">Financial summary</h2>
          <p className="mb-3 text-xs text-gray-400">
            Annual totals from AEC Party Returns — income, expenditure and outstanding debts.
          </p>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                <th className="py-2 pr-4">Year</th>
                <th className="py-2 pr-4 text-right">Total receipts</th>
                <th className="py-2 pr-4 text-right">Total payments</th>
                <th className="py-2 pr-4 text-right">Discretionary benefits</th>
                <th className="py-2 text-right">Total debts</th>
              </tr>
            </thead>
            <tbody>
              {party.financials.map((r) => (
                <tr key={r.financial_year} className="border-b border-gray-100">
                  <td className="py-2 pr-4">{r.financial_year}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {r.total_receipts != null
                      ? `$${r.total_receipts.toLocaleString("en-AU", { maximumFractionDigits: 0 })}`
                      : "—"}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {r.total_payments != null
                      ? `$${r.total_payments.toLocaleString("en-AU", { maximumFractionDigits: 0 })}`
                      : "—"}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {r.total_discretionary_benefits != null
                      ? `$${r.total_discretionary_benefits.toLocaleString("en-AU", { maximumFractionDigits: 0 })}`
                      : "—"}
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    {r.total_debts != null
                      ? `$${r.total_debts.toLocaleString("en-AU", { maximumFractionDigits: 0 })}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
