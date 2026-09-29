export function LoadingCard({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-slate-500">
        <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
        {label}
      </div>
      <div className="space-y-2">
        <div className="skeleton h-4 w-3/4" />
        <div className="skeleton h-4 w-1/2" />
        <div className="skeleton h-4 w-2/3" />
      </div>
    </div>
  );
}

export function ErrorCard({
  title,
  message,
  onRetry,
}: {
  title: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4"
    >
      <div className="font-semibold text-red-800">{title}</div>
      <div className="mt-1 text-sm text-red-700">
        {message ?? "The requested data could not be retrieved."}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 text-center">
      <div className="font-semibold text-slate-700">{title}</div>
      <div className="mt-1 text-sm text-slate-500">{message}</div>
    </div>
  );
}
