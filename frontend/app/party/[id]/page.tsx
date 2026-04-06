import { notFound } from "next/navigation";
import { fetchParty } from "../../lib/api";

export default async function PartyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const party = await fetchParty(id);
  if (!party) notFound();

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
          ${party.total_donations.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
        </p>
        <a
          href={`http://localhost:8000/api/v1/parties/${id}?format=csv`}
          className="mt-1 inline-block text-xs text-blue-600 hover:underline"
        >
          Download donations by year (CSV)
        </a>
      </div>

      {/* Donations by year */}
      {party.donations_by_year.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Donations by year</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="py-2 pr-4">Financial year</th>
                <th className="py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {party.donations_by_year.map((r) => (
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
      {party.industry_breakdown.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Donations by industry</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="py-2 pr-4">Industry</th>
                <th className="py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {party.industry_breakdown.slice(0, 20).map((r) => (
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
      {party.top_donors.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Top donors</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="py-2 pr-4">Donor</th>
                <th className="py-2 pr-4">Industry</th>
                <th className="py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {party.top_donors.map((r) => (
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
      {party.expenditure.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">Expenditure</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="py-2 pr-4">Year</th>
                <th className="py-2 pr-4">Category</th>
                <th className="py-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {party.expenditure.map((r, i) => (
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
    </div>
  );
}
