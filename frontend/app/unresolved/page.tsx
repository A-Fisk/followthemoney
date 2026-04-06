import { fetchUnresolved } from "../lib/api";

export const metadata = { title: "Unresolved Donors — Follow The Money" };

export default async function UnresolvedPage() {
  const donors = await fetchUnresolved();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Unresolved donor entities</h1>
        <p className="mt-1 text-sm text-gray-500">
          Donor entities the pipeline couldn't identify via ABR. Sorted by
          total amount donated. These are open research leads.
        </p>
      </div>

      {!donors || donors.length === 0 ? (
        <p className="text-gray-500">No unresolved donors found.</p>
      ) : (
        <>
          <p className="text-sm text-gray-500">{donors.length} entities</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4 text-right">Total donated</th>
                  <th className="py-2">Notes</th>
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
