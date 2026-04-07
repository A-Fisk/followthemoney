import { fetchUnresolved, UnresolvedDonor } from "../lib/api";

export const metadata = { title: "Unresolved Donors — Follow The Money" };

type USort = "name" | "type" | "total" | "notes";

function sortUnresolved(donors: UnresolvedDonor[], sort: USort): UnresolvedDonor[] {
  return [...donors].sort((a, b) => {
    if (sort === "name")  return a.name.localeCompare(b.name);
    if (sort === "type")  return (a.entity_type ?? "").localeCompare(b.entity_type ?? "");
    if (sort === "notes") return (a.notes ?? "").localeCompare(b.notes ?? "");
    return b.total_donated - a.total_donated;
  });
}

function sortLink(label: string, key: USort, current: USort, className?: string) {
  const active = current === key;
  return (
    <a
      href={`?sort=${key}`}
      className={`${className ?? ""} ${active ? "font-semibold text-gray-800" : "text-gray-500 hover:text-gray-700"}`}
    >
      {label}{active ? " ↓" : ""}
    </a>
  );
}

export default async function UnresolvedPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort } = await searchParams;
  const uSort: USort = sort === "name" || sort === "type" || sort === "notes" ? sort : "total";

  const raw = await fetchUnresolved();
  const donors = raw ? sortUnresolved(raw, uSort) : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Unresolved donor entities</h1>
        <p className="mt-1 text-sm text-gray-500">
          Donor entities the pipeline couldn&apos;t identify via ABR. These are open research leads.
        </p>
      </div>

      {donors.length === 0 ? (
        <p className="text-gray-500">No unresolved donors found.</p>
      ) : (
        <>
          <p className="text-sm text-gray-500">{donors.length} entities</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide">
                  <th className="py-2 pr-4">{sortLink("Name",         "name",  uSort)}</th>
                  <th className="py-2 pr-4">{sortLink("Type",         "type",  uSort)}</th>
                  <th className="py-2 pr-4 text-right">{sortLink("Total donated", "total", uSort)}</th>
                  <th className="py-2">    {sortLink("Notes",         "notes", uSort)}</th>
                </tr>
              </thead>
              <tbody>
                {donors.map((d) => (
                  <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 pr-4">
                      <a href={`/donor/${d.id}`} className="text-blue-600 hover:underline font-medium">
                        {d.name}
                      </a>
                    </td>
                    <td className="py-2 pr-4 text-gray-500">{d.entity_type || "—"}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      ${d.total_donated.toLocaleString("en-AU", { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-2 text-gray-500 text-xs">{d.notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-400">
            Data from AEC Transparency Register.{" "}
            <a
              href="http://localhost:8000/api/v1/unresolved?format=csv"
              className="underline hover:text-gray-600"
            >
              Download CSV
            </a>
          </p>
        </>
      )}
    </div>
  );
}
