/**
 * Shield Dashboard — Transaction Log
 *
 * Shows the last 100 transactions for the hardcoded test rights holder.
 * Auto-refreshes every 10 seconds.
 *
 * Requires NEXT_PUBLIC_GATEWAY_URL (defaults to http://localhost:8000) and
 * NEXT_PUBLIC_CLIENT_ID / NEXT_PUBLIC_CLIENT_SECRET for the gateway auth token.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

const GATEWAY = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
const CLIENT_ID = process.env.NEXT_PUBLIC_CLIENT_ID || "test-tool";
const CLIENT_SECRET = process.env.NEXT_PUBLIC_CLIENT_SECRET || "test-secret";
const RIGHTS_HOLDER_ID = process.env.NEXT_PUBLIC_RIGHTS_HOLDER_ID || "test-rights-holder";
const REFRESH_INTERVAL_MS = 10_000;

// ─── token cache ──────────────────────────────────────────────────────────────
let _cachedToken = null;
let _tokenExpiresAt = 0;

async function getToken() {
  if (_cachedToken && Date.now() / 1000 < _tokenExpiresAt - 60) return _cachedToken;

  const form = new URLSearchParams();
  form.append("client_id", CLIENT_ID);
  form.append("client_secret", CLIENT_SECRET);

  const resp = await fetch(`${GATEWAY}/auth/token`, { method: "POST", body: form });
  if (!resp.ok) throw new Error(`Auth failed: ${resp.status}`);
  const data = await resp.json();
  _cachedToken = data.access_token;
  _tokenExpiresAt = Date.now() / 1000 + (data.expires_in || 3600);
  return _cachedToken;
}

async function fetchTransactions() {
  const token = await getToken();
  const resp = await fetch(
    `${GATEWAY}/v1/transactions?rights_holder_id=${encodeURIComponent(RIGHTS_HOLDER_ID)}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!resp.ok) throw new Error(`Failed to load transactions: ${resp.status}`);
  return resp.json();
}

function DecisionBadge({ decision }) {
  const cls = {
    approve: "badge badge-approve",
    reject: "badge badge-reject",
    escalate: "badge badge-escalate",
  }[decision] || "badge";
  return <span className={cls}>{decision}</span>;
}

function truncate(str, n = 12) {
  return str ? str.slice(0, n) + "…" : "—";
}

function formatTs(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function TransactionLog() {
  const [txns, setTxns] = useState(null);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const timerRef = useRef(null);

  async function load() {
    try {
      const data = await fetchTransactions();
      setTxns(data);
      setError(null);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    timerRef.current = setInterval(load, REFRESH_INTERVAL_MS);
    return () => clearInterval(timerRef.current);
  }, []);

  return (
    <>
      <nav>
        <span className="brand">Shield</span>
        <Link href="/" className="active">Transaction Log</Link>
        <Link href="/detect">Watermark Checker</Link>
      </nav>

      <div className="page">
        <h1>
          Transaction Log
          {lastRefresh && (
            <span className="refresh-note">
              Auto-refreshes every 10 s — last: {lastRefresh.toLocaleTimeString()}
            </span>
          )}
        </h1>

        {error && <div className="error-msg">{error}</div>}

        {txns === null && !error && <div className="loading">Loading…</div>}

        {txns !== null && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Request ID</th>
                  <th>Use Type</th>
                  <th>Decision</th>
                  <th>End User</th>
                  <th>Watermarked</th>
                </tr>
              </thead>
              <tbody>
                {txns.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", color: "#94a3b8", padding: "2rem" }}>
                      No transactions yet.
                    </td>
                  </tr>
                ) : (
                  txns.map((t) => (
                    <tr key={t.request_id}>
                      <td>{formatTs(t.created_at)}</td>
                      <td title={t.request_id} style={{ fontFamily: "monospace" }}>
                        {truncate(t.request_id, 14)}
                      </td>
                      <td>{t.use_type || "—"}</td>
                      <td><DecisionBadge decision={t.decision} /></td>
                      <td>{t.end_user_id}</td>
                      <td>{t.watermarked ? "✓" : "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
