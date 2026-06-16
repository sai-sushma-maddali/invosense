import { citedPublish } from "../lib/cited.js";
import type { Decision } from "./pay.js";
import type { PaymentResult } from "./pay.js";

export interface PublishResult {
  url: string;       // cited.md permalink
  record_id: string;
}

/**
 * Publish a decision + payment record to cited.md.
 *
 * Falls back to stub mode (no network call) when CITED_API_URL is unset,
 * so local development never requires live cited.md credentials.
 */
export async function publish(
  decision: Decision,
  payment: PaymentResult
): Promise<PublishResult> {
  const published_at = new Date().toISOString();

  const result = await citedPublish({
    invoice_id:   decision.invoice_id,
    decision:     decision.decision,
    reasons:      decision.reasons,
    tax_rule_url: decision.tax_rule_url,
    tx_hash:      payment.tx_hash,
    amount_usd:   payment.amount_usd,
    network:      "base-sepolia",
    published_at,
  });

  console.log(
    `[PUBLISH] ${decision.invoice_id} | ${result.url} | record_id=${result.id} | ${published_at}`
  );

  return { url: result.url, record_id: result.id };
}
