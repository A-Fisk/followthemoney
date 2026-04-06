import { Suspense } from "react";
import { fetchSearch } from "../lib/api";
import SearchInput from "./SearchInput";

const TYPE_LABELS: Record<string, string> = {
  politician: "Politician",
  party: "Party",
  donor: "Donor",
};

const TYPE_HREF: Record<string, string> = {
  politician: "/politician",
  party: "/party",
  donor: "/donor",
};

const TYPE_COLOURS: Record<string, string> = {
  politician: "bg-blue-50 text-blue-700",
  party: "bg-purple-50 text-purple-700",
  donor: "bg-green-50 text-green-700",
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const params = await searchParams;
  const q = params.q?.trim() || "";
  const results = q.length >= 2 ? await fetchSearch(q) : null;

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">Search</h1>
      <Suspense>
        <SearchInput defaultValue={q} />
      </Suspense>

      {q.length > 0 && q.length < 2 && (
        <p className="text-sm text-gray-400">Enter at least 2 characters.</p>
      )}

      {results && (
        <>
          {results.results.length === 0 ? (
            <p className="text-sm text-gray-500">No results for "{q}".</p>
          ) : (
            <div className="space-y-1">
              <p className="text-xs text-gray-400">{results.results.length} results</p>
              {results.results.map((r) => (
                <a
                  key={`${r.type}-${r.id}`}
                  href={`${TYPE_HREF[r.type]}/${r.id}`}
                  className="flex items-center gap-3 rounded border border-gray-100 px-4 py-3 hover:border-gray-300 hover:bg-gray-50 transition"
                >
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${TYPE_COLOURS[r.type]}`}>
                    {TYPE_LABELS[r.type]}
                  </span>
                  <span className="font-medium">{r.name}</span>
                  {r.secondary && (
                    <span className="text-sm text-gray-400">{r.secondary}</span>
                  )}
                </a>
              ))}
            </div>
          )}
        </>
      )}

      {!q && (
        <div className="text-sm text-gray-500 space-y-1">
          <p>Try: "Hancock", "Labor", "BHP", "Rinehart", "Greens"</p>
        </div>
      )}
    </div>
  );
}
