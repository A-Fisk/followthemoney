import { notFound } from "next/navigation";
import { fetchDonor, DonationByPartyRow } from "../../lib/api";

type DonationSort = "amount" | "recipient" | "year";

function sortDonations(donations: DonationByPartyRow[], sort: DonationSort): DonationByPartyRow[] {
  return [...donations].sort((a, b) => {
    if (sort === "amount") return b.amount - a.amount;
    if (sort === "year")   return (b.financial_year ?? "").localeCompare(a.financial_year ?? "");
    // recipient: party name or politician name
    const nameA = a.party?.name ?? a.politician_name ?? "";
    const nameB = b.party?.name ?? b.politician_name ?? "";
    return nameA.localeCompare(nameB);
  });
}

export default async function DonorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ sort?: string }>;
}) {
  const { id } = await params;
  const { sort } = await searchParams;
  const donationSort: DonationSort = sort === "recipient" || sort === "year" ? sort : "amount";

  const donor = await fetchDonor(id);
  if (!donor) notFound();

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
        <p className="mt-3 text-lg font-semibold">
          Total donated:{" "}
          <span className="text-gray-700">
            ${donor.total_donated.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
          </span>
        </p>
      </div>

      {/* By party */}
      {donor.donations_by_party.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Donations by party</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="py-2 pr-4">Party</th>
                <th className="py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {donor.donations_by_party.map((r, i) => (
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
            <div className="flex items-center gap-4">
              <h2 className="font-semibold text-gray-900">
                All donations{" "}
                <span className="text-gray-400 font-normal text-sm">({donor.donations.length})</span>
              </h2>
              <span className="text-xs text-gray-400">
                Sort:{" "}
                {(["amount", "recipient", "year"] as DonationSort[]).map((s) => (
                  <a
                    key={s}
                    href={`?sort=${s}`}
                    className={`mr-2 ${donationSort === s ? "font-semibold text-gray-700" : "text-blue-600 hover:underline"}`}
                  >
                    {s}
                  </a>
                ))}
              </span>
            </div>
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
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">Year</th>
                  <th className="py-2 pr-4 text-right">Amount</th>
                  <th className="py-2 pr-4">Recipient</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {sortDonations(donor.donations, donationSort).map((d) => (
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
