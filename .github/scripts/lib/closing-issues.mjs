/**
 * Same semantics as the Closes/Fixes/Resolves parsing already inlined in
 * pr-lifecycle.mjs and validate-pr.mjs, extracted here because link-backfill.mjs
 * and close-guard.mjs both depend on seeing the exact same issue numbers — a
 * drift between copies here would silently break the dual-verification guarantee.
 */
export function parseClosingIssueNumbers(body) {
  return [
    ...new Set(
      [...String(body ?? '').matchAll(/\b(?:Closes|Fixes|Resolves)\s+#(\d+)/gi)].map((match) =>
        Number(match[1]),
      ),
    ),
  ];
}

/**
 * referencingPRs: [{ number, state }], state in 'OPEN' | 'CLOSED' | 'MERGED'.
 * Order matters: a merged PR always allows the close even if another (stale)
 * PR referencing the same issue is still open.
 */
export function decideCloseAction(referencingPRs) {
  if (referencingPRs.length === 0) return { action: 'allow', reason: 'no-referencing-prs' };

  const merged = referencingPRs.filter((pr) => pr.state === 'MERGED');
  if (merged.length > 0) return { action: 'allow', reason: 'merged-pr-found', merged };

  const open = referencingPRs.filter((pr) => pr.state === 'OPEN');
  if (open.length > 0) return { action: 'block', reason: 'open-pr-pending', open };

  return { action: 'allow', reason: 'all-referencing-prs-abandoned' };
}
