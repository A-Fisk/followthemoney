export default function Home() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">AusPol Transparency</h1>
      <p className="text-gray-600 max-w-2xl">
        Public record, in one place. All data sourced directly from the AEC
        Transparency Register, Parliament House Register of Interests, and They
        Vote For You.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <a
          href="/search"
          className="rounded border border-gray-200 p-5 hover:border-gray-400 transition"
        >
          <h2 className="font-semibold">Search</h2>
          <p className="text-sm text-gray-500 mt-1">
            Find politicians, parties, and donors
          </p>
        </a>
        <a
          href="/search?q=Labor"
          className="rounded border border-gray-200 p-5 hover:border-gray-400 transition"
        >
          <h2 className="font-semibold">Parties</h2>
          <p className="text-sm text-gray-500 mt-1">
            Donation totals, expenditure, top donors by party
          </p>
        </a>
        <a
          href="/unresolved"
          className="rounded border border-gray-200 p-5 hover:border-gray-400 transition"
        >
          <h2 className="font-semibold">Unresolved donors</h2>
          <p className="text-sm text-gray-500 mt-1">
            Entities we couldn't identify — open research leads
          </p>
        </a>
        <a
          href="/api/docs"
          className="rounded border border-gray-200 p-5 hover:border-gray-400 transition"
        >
          <h2 className="font-semibold">API</h2>
          <p className="text-sm text-gray-500 mt-1">
            Swagger docs at /api/docs
          </p>
        </a>
      </div>
    </div>
  );
}
