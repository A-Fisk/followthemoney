import React from "react";
import { notFound } from "next/navigation";
import { fetchPolitician, VoteRow, PolicyPosition } from "../../lib/api";

// Australian federal parliaments covered by TVFY
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
    if (voteDate >= p.start && (p.end === null || voteDate <= p.end)) {
      return p.number;
    }
  }
  return null;
}

function buildUrl(params: Record<string, string | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "?";
}

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

type VoteSort = "date" | "vote" | "issue";

function sortVotes(votes: VoteRow[], sort: VoteSort): VoteRow[] {
  return [...votes].sort((a, b) => {
    if (sort === "date") {
      return (b.vote_date ?? "").localeCompare(a.vote_date ?? "");
    }
    if (sort === "vote") {
      return (a.vote_direction ?? "").localeCompare(b.vote_direction ?? "");
    }
    // issue: sort by first tag
    const ta = a.issue_tags?.[0] ?? "zzz";
    const tb = b.issue_tags?.[0] ?? "zzz";
    return ta.localeCompare(tb);
  });
}

export default async function PoliticianPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ sort?: string; parliament?: string }>;
}) {
  const { id } = await params;
  const { sort, parliament } = await searchParams;
  const voteSort: VoteSort = sort === "vote" || sort === "issue" ? sort : "date";
  const selectedParliament = parliament ? Number(parliament) : null;

  const pol = await fetchPolitician(id);
  if (!pol) notFound();

  const chamberLabel = pol.chamber === "house" ? "House of Representatives" : pol.chamber === "senate" ? "Senate" : null;

  // Determine which parliaments this politician has votes in
  const parliamentsWithVotes = [
    ...new Set(pol.votes.map((v) => voteParliament(v.vote_date)).filter((n): n is number => n !== null)),
  ].sort((a, b) => b - a);

  const filteredVotes = selectedParliament
    ? pol.votes.filter((v) => voteParliament(v.vote_date) === selectedParliament)
    : pol.votes;

  const sortedVotes = sortVotes(filteredVotes, voteSort);

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

      {/* Party top donors */}
      {pol.party && pol.party_top_donors.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">
              Top donors to{" "}
              <a href={`/party/${pol.party.id}`} className="text-blue-600 hover:underline">
                {pol.party.abbreviation || pol.party.name}
              </a>{" "}
              <span className="font-normal text-gray-400 text-sm">(top 10)</span>
            </h2>
            <a href={`/party/${pol.party.id}`} className="text-xs text-blue-600 hover:underline">
              Full party profile →
            </a>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Donor</th>
                  <th className="py-2 pr-4">Industry</th>
                  <th className="py-2 text-right">Total donated</th>
                </tr>
              </thead>
              <tbody>
                {pol.party_top_donors.map((d, i) => (
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
          <span className="font-normal text-gray-400 text-sm">({pol.interests.length})</span>
        </h2>
        {pol.interests.length === 0 ? (
          <p className="text-sm text-gray-400">No declared interests on record.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4">Provider</th>
                  <th className="py-2 pr-4">Received</th>
                  <th className="py-2 pr-4">Declared</th>
                  <th className="py-2 pr-4">Days late</th>
                  <th className="py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {pol.interests.map((i) => (
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
                    <td className="py-2 pr-4 text-xs">
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
        )}
      </section>

      {/* Direct donations */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">
            Direct donations received{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({pol.direct_donations.length})
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">Year</th>
                  <th className="py-2 pr-4 text-right">Amount</th>
                  <th className="py-2 pr-4">Donor</th>
                  <th className="py-2 pr-4">Industry</th>
                  <th className="py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {pol.direct_donations.map((d) => (
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
                    <td className="py-2 pr-4 text-gray-500 text-xs">
                      {d.donor?.industry_label || "—"}
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
        )}
      </section>

      {/* Via party branch donations */}
      {pol.via_party_donations.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Donations via named party branch{" "}
            <span className="font-normal text-gray-400 text-sm">({pol.via_party_donations.length})</span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">Year</th>
                  <th className="py-2 pr-4 text-right">Amount</th>
                  <th className="py-2 pr-4">Donor</th>
                  <th className="py-2 pr-4">Party branch</th>
                  <th className="py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {pol.via_party_donations.map((d) => (
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
        </section>
      )}

      {/* Donations made as a donor */}
      {pol.as_donor_donations.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-gray-900">
            Donations made{" "}
            <span className="font-normal text-gray-400 text-sm">({pol.as_donor_donations.length})</span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">Year</th>
                  <th className="py-2 pr-4 text-right">Amount</th>
                  <th className="py-2 pr-4">Donor name</th>
                  <th className="py-2 pr-4">Recipient</th>
                  <th className="py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {pol.as_donor_donations.map((d) => (
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
        </section>
      )}

      {/* Voting record */}
      <section>
        <div className="mb-2 flex flex-wrap items-center gap-4">
          <h2 className="font-semibold text-gray-900">
            Voting record{" "}
            <span className="font-normal text-gray-400 text-sm">
              ({filteredVotes.length}{selectedParliament ? ` in ${selectedParliament}th Parliament` : ` of ${pol.votes.length}`})
            </span>
          </h2>
          {pol.votes.length > 0 && (
            <span className="text-xs text-gray-400">
              Sort:{" "}
              {(["date", "vote", "issue"] as VoteSort[]).map((s) => (
                <a
                  key={s}
                  href={buildUrl({ sort: s, parliament: parliament })}
                  className={`mr-2 ${voteSort === s ? "font-semibold text-gray-700" : "text-blue-600 hover:underline"}`}
                >
                  {s}
                </a>
              ))}
            </span>
          )}
        </div>
        {parliamentsWithVotes.length > 1 && (
          <div className="mb-3 flex flex-wrap gap-1 text-xs">
            <a
              href={buildUrl({ sort: voteSort !== "date" ? voteSort : undefined })}
              className={`rounded px-2 py-1 ${!selectedParliament ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
            >
              All
            </a>
            {parliamentsWithVotes.map((p) => (
              <a
                key={p}
                href={buildUrl({ sort: voteSort !== "date" ? voteSort : undefined, parliament: String(p) })}
                className={`rounded px-2 py-1 ${selectedParliament === p ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
              >
                {p}th
              </a>
            ))}
          </div>
        )}
        {pol.votes.length === 0 ? (
          <p className="text-sm text-gray-400">No voting record on file.</p>
        ) : filteredVotes.length === 0 ? (
          <p className="text-sm text-gray-400">No votes found for the {selectedParliament}th Parliament.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">Date</th>
                  <th className="py-2 pr-4">Vote</th>
                  <th className="py-2 pr-4">Bill / Motion</th>
                  <th className="py-2">Issues</th>
                </tr>
              </thead>
              <tbody>
                {sortedVotes.map((v) => {
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
                          <a
                            href={link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline"
                          >
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
