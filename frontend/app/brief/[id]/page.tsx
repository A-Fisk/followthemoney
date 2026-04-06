import { notFound } from "next/navigation";
import { fetchPolitician } from "../../lib/api";

export default async function BriefPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ topic?: string }>;
}) {
  const { id } = await params;
  const { topic } = await searchParams;

  const pol = await fetchPolitician(id);
  if (!pol) notFound();

  const chamberLabel = pol.chamber === "house" ? "House" : pol.chamber === "senate" ? "Senate" : null;

  // Donations from the last 3 financial years, grouped by industry, optionally filtered by topic
  const recentYears = new Set(
    pol.direct_donations
      .map((d) => d.financial_year)
      .sort()
      .reverse()
      .slice(0, 3)
  );

  const relevantDonations = pol.direct_donations.filter(
    (d) =>
      recentYears.has(d.financial_year) &&
      (!topic ||
        d.donor?.industry_label?.toLowerCase().includes(topic.toLowerCase()))
  );

  // Aggregate by industry label
  const byIndustry = new Map<string, number>();
  for (const d of relevantDonations) {
    const label = d.donor?.industry_label || "Other";
    byIndustry.set(label, (byIndustry.get(label) ?? 0) + d.amount);
  }
  const industryRows = [...byIndustry.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  const totalRecent = relevantDonations.reduce((s, d) => s + d.amount, 0);

  const yearRange =
    recentYears.size > 0
      ? `${[...recentYears].sort()[0]} to ${[...recentYears].sort().reverse()[0]}`
      : "recent years";

  const quickCopy =
    totalRecent > 0
      ? `According to AEC records (https://transparency.aec.gov.au), ${pol.name}${pol.party ? ` (${pol.party.abbreviation || pol.party.name})` : ""} or their party received $${totalRecent.toLocaleString("en-AU", { maximumFractionDigits: 0 })} from ${topic || "private"} donors between ${yearRange}.`
      : null;

  const recentInterests = pol.interests
    .filter((i) => !topic || i.donor?.name.toLowerCase().includes(topic.toLowerCase()))
    .slice(0, 5);

  return (
    <div className="max-w-lg mx-auto space-y-6 print:text-sm">
      {/* Identity bar */}
      <div className="border-b border-gray-200 pb-4">
        <h1 className="text-xl font-bold">{pol.name}</h1>
        <p className="text-sm text-gray-600">
          {[pol.party?.name, chamberLabel, pol.electorate].filter(Boolean).join(" · ")}
        </p>
        {topic && (
          <p className="mt-1 text-xs text-blue-600 bg-blue-50 inline-block px-2 py-0.5 rounded">
            Filtered: {topic}
          </p>
        )}
      </div>

      {/* Donor snapshot */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
          Donor snapshot — last 3 years{topic ? ` · ${topic}` : ""}
        </h2>
        {industryRows.length === 0 ? (
          <p className="text-sm text-gray-400">
            No direct donations on record.{" "}
            <a href={`/party/${pol.party?.id}`} className="text-blue-600 hover:underline">
              Check party profile →
            </a>
          </p>
        ) : (
          <div className="space-y-1">
            {industryRows.map(([label, total]) => (
              <div key={label} className="flex justify-between text-sm">
                <span className="text-gray-700">{label}</span>
                <span className="tabular-nums font-medium">
                  ${total.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Declared interests */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
          Declared interests (gifts & travel)
        </h2>
        {recentInterests.length === 0 ? (
          <p className="text-sm text-gray-400">None on record.</p>
        ) : (
          <div className="space-y-2">
            {recentInterests.map((i) => (
              <div key={i.id} className="text-sm border-l-2 border-gray-200 pl-3">
                <p className="text-gray-700 leading-snug">{i.description || "—"}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {i.donor?.name && (
                    <span className="mr-2">
                      <a href={`/donor/${i.donor.id}`} className="text-blue-500 hover:underline">
                        {i.donor.name}
                      </a>
                    </span>
                  )}
                  {i.date_declared && <span>Declared {i.date_declared}</span>}
                  {i.days_late != null && i.days_late > 0 && (
                    <span className="ml-2 text-red-600 font-medium">+{i.days_late} days late</span>
                  )}
                </p>
              </div>
            ))}
            {pol.interests.length > 5 && (
              <a href={`/politician/${id}`} className="text-xs text-blue-600 hover:underline">
                +{pol.interests.length - 5} more →
              </a>
            )}
          </div>
        )}
      </section>

      {/* Quick copy */}
      {quickCopy && (
        <section>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Quick copy
          </h2>
          <pre className="whitespace-pre-wrap text-xs bg-gray-50 border border-gray-200 rounded p-3 leading-relaxed text-gray-700 font-sans select-all">
            {quickCopy}
          </pre>
        </section>
      )}

      {/* Full profile link */}
      <div className="border-t border-gray-200 pt-4 flex items-center justify-between text-sm">
        <a href={`/politician/${id}`} className="text-blue-600 hover:underline font-medium">
          Full profile →
        </a>
        <span className="text-xs text-gray-400">
          Source:{" "}
          <a href="https://transparency.aec.gov.au" target="_blank" rel="noopener noreferrer"
             className="underline">AEC</a>{" "}
          ·{" "}
          <a href="https://www.aph.gov.au/Senators_and_Members/Members/Register"
             target="_blank" rel="noopener noreferrer" className="underline">Register of Interests</a>
        </span>
      </div>
    </div>
  );
}
