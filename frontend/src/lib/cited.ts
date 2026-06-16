import "dotenv/config";

export interface CitedPayload {
  invoice_id: string;
  decision: "PAY" | "FLAG" | "HUMAN_REVIEW";
  reasons: string[];
  tax_rule_url: string;
  tx_hash: string;
  amount_usd: number;
  network: "base-sepolia";
  published_at: string; // ISO-8601
}

interface CitedResponse {
  url: string;
  id: string;
}

/**
 * Thin wrapper around the cited.md publish endpoint.
 *
 * If CITED_API_URL is unset the call is stubbed so the rest of the pipeline
 * never breaks during development. The stub URL is clearly marked as fake.
 */
export async function citedPublish(payload: CitedPayload): Promise<CitedResponse> {
  const apiUrl = process.env.CITED_API_URL;
  const apiKey = process.env.CITED_API_KEY;

  // ── Stub mode ──────────────────────────────────────────────────────────────
  if (!apiUrl) {
    console.warn(
      "[CITED] CITED_API_URL not set — returning stub response. " +
        "Set CITED_API_URL in .env to publish to real cited.md."
    );
    const stubId = `stub-${payload.invoice_id}-${Date.now()}`;
    return {
      url: `https://stub.cited.md/records/${stubId}`,
      id: stubId,
    };
  }

  // ── Real endpoint ──────────────────────────────────────────────────────────
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": "invo-frontend/1.0",
  };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const res = await fetch(apiUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "(no body)");
    throw new Error(`cited.md returned HTTP ${res.status}: ${text}`);
  }

  const data = (await res.json()) as CitedResponse;
  return data;
}
