/**
 * Shield Dashboard — Watermark Checker
 *
 * Accepts a file upload, calls POST /v1/detect, and displays the result.
 */

import { useRef, useState } from "react";
import Link from "next/link";

const GATEWAY = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";

async function detectWatermark(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  // Convert to base64
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  const b64 = btoa(binary);

  const resp = await fetch(`${GATEWAY}/v1/detect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image: b64 }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

function MetaRow({ label, value }) {
  if (!value) return null;
  return (
    <div className="meta-item">
      <strong>{label}:</strong> {String(value)}
    </div>
  );
}

export default function DetectPage() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function handleFileChange(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setResult(null);
    setError(null);
  }

  async function handleCheck() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const data = await detectWatermark(file);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <nav>
        <span className="brand">Shield</span>
        <Link href="/">Transaction Log</Link>
        <Link href="/detect" className="active">Watermark Checker</Link>
      </nav>

      <div className="page">
        <h1>Watermark Checker</h1>

        {/* Upload zone */}
        <label>
          <div
            className="upload-zone"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files?.[0];
              if (f) { setFile(f); setResult(null); setError(null); }
            }}
          >
            {file ? (
              <>
                <div style={{ fontSize: "1rem", fontWeight: 600 }}>{file.name}</div>
                <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 4 }}>
                  {(file.size / 1024).toFixed(1)} KB
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: "2rem", marginBottom: 8 }}>🖼️</div>
                <div style={{ fontWeight: 600 }}>Drop an image here or click to browse</div>
                <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 4 }}>
                  Supports JPEG and PNG
                </div>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/jpg"
            onChange={handleFileChange}
          />
        </label>

        <button
          className="btn"
          onClick={handleCheck}
          disabled={!file || loading}
        >
          {loading ? "Checking…" : "Check for Shield watermark"}
        </button>

        {error && <div className="error-msg" style={{ marginTop: "1rem" }}>{error}</div>}

        {result && (
          <div className="card">
            {result.found ? (
              <>
                <div className="found-yes" style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>
                  ✓ Shield watermark detected
                </div>
                <div className="meta-row">
                  <MetaRow label="Generation ID" value={result.generation_id} />
                </div>
                {result.transaction && (
                  <>
                    <hr style={{ margin: "0.75rem 0", borderColor: "#f1f5f9" }} />
                    <div style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.5rem", color: "#475569" }}>
                      Transaction details
                    </div>
                    <div className="meta-row">
                      <MetaRow label="Rights holder" value={result.transaction.rights_holder_id} />
                      <MetaRow label="Client" value={result.transaction.client_id} />
                      <MetaRow label="End user" value={result.transaction.end_user_id} />
                      <MetaRow label="Decision" value={result.transaction.decision} />
                      <MetaRow
                        label="Created"
                        value={result.transaction.created_at
                          ? new Date(result.transaction.created_at).toLocaleString()
                          : null}
                      />
                      <MetaRow label="SHA-256" value={result.transaction.output_hash} />
                    </div>
                    {result.transaction.metadata && (
                      <div style={{ marginTop: "0.75rem" }}>
                        <div style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.25rem", color: "#475569" }}>
                          Policy metadata
                        </div>
                        <pre style={{
                          background: "#f8fafc", borderRadius: 4,
                          padding: "0.5rem", fontSize: "0.75rem",
                          overflowX: "auto", color: "#334155"
                        }}>
                          {JSON.stringify(result.transaction.metadata, null, 2)}
                        </pre>
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="found-no" style={{ fontSize: "1rem" }}>
                No Shield watermark detected in this image.
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
