/**
 * A request that failed: what went wrong, and a way to run it again. Used wherever a view
 * loads data, so a backend that is down never reads as "nothing here yet".
 */
export function LoadError({ error, onRetry, className = "" }: { error: string; onRetry?: () => void; className?: string }) {
  return (
    <div className={`alert flex flex-wrap items-center gap-x-3 gap-y-2 ${className}`} role="alert">
      <span className="min-w-0 flex-1">{error}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-ghost h-8 shrink-0 px-3 text-xs">
          Try again
        </button>
      )}
    </div>
  );
}
