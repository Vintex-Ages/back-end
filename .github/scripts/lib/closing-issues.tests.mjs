import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decideCloseAction, parseClosingIssueNumbers } from './closing-issues.mjs';

test('decideCloseAction: no referencing PRs allows the close', () => {
  assert.deepEqual(decideCloseAction([]), { action: 'allow', reason: 'no-referencing-prs' });
});

test('decideCloseAction: a merged PR allows the close', () => {
  const result = decideCloseAction([{ number: 1, state: 'MERGED' }]);
  assert.equal(result.action, 'allow');
  assert.equal(result.reason, 'merged-pr-found');
});

test('decideCloseAction: an open PR blocks the close', () => {
  const result = decideCloseAction([{ number: 1, state: 'OPEN' }]);
  assert.equal(result.action, 'block');
  assert.equal(result.reason, 'open-pr-pending');
  assert.deepEqual(result.open, [{ number: 1, state: 'OPEN' }]);
});

test('decideCloseAction: a single abandoned (closed, unmerged) PR allows the close', () => {
  const result = decideCloseAction([{ number: 1, state: 'CLOSED' }]);
  assert.equal(result.action, 'allow');
  assert.equal(result.reason, 'all-referencing-prs-abandoned');
});

test('decideCloseAction: multiple abandoned PRs still allow the close', () => {
  const result = decideCloseAction([
    { number: 1, state: 'CLOSED' },
    { number: 2, state: 'CLOSED' },
  ]);
  assert.equal(result.action, 'allow');
});

test('decideCloseAction: a merged PR wins over a stale open PR', () => {
  const result = decideCloseAction([
    { number: 1, state: 'OPEN' },
    { number: 2, state: 'MERGED' },
  ]);
  assert.equal(result.action, 'allow');
  assert.equal(result.reason, 'merged-pr-found');
});

test('decideCloseAction: an open PR still blocks even next to an abandoned one', () => {
  const result = decideCloseAction([
    { number: 1, state: 'OPEN' },
    { number: 2, state: 'CLOSED' },
  ]);
  assert.equal(result.action, 'block');
});

test('parseClosingIssueNumbers: matches Closes/Fixes/Resolves case-insensitively', () => {
  const body = 'closes #1\nFixes #2\nRESOLVES #3';
  assert.deepEqual(parseClosingIssueNumbers(body), [1, 2, 3]);
});

test('parseClosingIssueNumbers: dedupes repeated references', () => {
  assert.deepEqual(parseClosingIssueNumbers('Closes #5, also Closes #5 again'), [5]);
});

test('parseClosingIssueNumbers: no match returns an empty array', () => {
  assert.deepEqual(parseClosingIssueNumbers('just a regular description'), []);
});

test('parseClosingIssueNumbers: handles null/undefined body', () => {
  assert.deepEqual(parseClosingIssueNumbers(null), []);
  assert.deepEqual(parseClosingIssueNumbers(undefined), []);
});
