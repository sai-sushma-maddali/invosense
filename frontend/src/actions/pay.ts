import "dotenv/config";
import { createPublicClient, http, parseUnits, encodeFunctionData } from "viem";
import { baseSepolia } from "viem/chains";
import { getTestWalletClient, requireBaseSepolia, REQUIRED_NETWORK } from "../lib/wallet.js";

// ── Interfaces ─────────────────────────────────────────────────────────────

export interface Decision {
  invoice_id: string;
  vendor: string;
  amount_myr: number;
  currency: "MYR";
  decision: "PAY" | "FLAG" | "HUMAN_REVIEW";
  reasons: string[];
  tax_rule_url: string;
  line_items: LineItem[];
  /** Optional OCR provenance — populated when the invoice comes from the OCR pipeline (out/). */
  ocr?: OcrMeta;
}

export interface LineItem {
  description: string;
  qty: number;
  unit_price: number;
}

/** Raw OCR-extracted fields, per-field confidence, bounding boxes and the annotated image. */
export interface OcrMeta {
  company: string;
  gst_id?: string;
  invoice_no?: string;
  date?: string;
  taxable?: number;
  tax?: number;
  total: number;
  confidence: Record<string, number>;
  overall_confidence: number;
  /** [x, y, width, height] in image pixels, keyed by field name. */
  boxes: Record<string, number[]>;
  /** URL the frontend can use to load the annotated invoice image. */
  image_url: string;
}

export interface PaymentResult {
  tx_hash: string;
  network: "base-sepolia";
  amount_usd: number; // converted testnet USDC
  timestamp: string; // ISO-8601
}

// ── Constants ──────────────────────────────────────────────────────────────

// MOCK FX RATE — clearly labelled, not a real exchange rate.
// Used only for testnet demo payments.
const MOCK_FX_MYR_TO_USDC = parseFloat(process.env.MOCK_FX_MYR_TO_USDC ?? "0.22");

// Base Sepolia USDC contract (Circle's official testnet deployment)
const USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e" as const;

// Minimal ERC-20 transfer ABI fragment
const ERC20_TRANSFER_ABI = [
  {
    name: "transfer",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [
      { name: "to", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
] as const;

// x402 protocol — recipient address for testnet payments.
// In a real x402 flow this comes from the HTTP 402 challenge response.
// For the demo we use a well-known Base Sepolia test address.
const X402_RECIPIENT =
  (process.env.X402_RECIPIENT as `0x${string}` | undefined) ??
  "0x000000000000000000000000000000000000dEaD"; // burn address for testnet demos

// ── Helpers ────────────────────────────────────────────────────────────────

/** MOCK FX — convert MYR to USDC. Not a real rate. */
function myrToUsdc(amountMyr: number): number {
  // MOCK FX: 1 MYR = MOCK_FX_MYR_TO_USDC USDC (testnet only)
  return Math.round(amountMyr * MOCK_FX_MYR_TO_USDC * 100) / 100;
}

/**
 * Simulate a payment tx (used when WALLET_PRIVATE_KEY is not set).
 * Returns a realistic-looking but fake Sepolia tx hash so the rest of
 * the pipeline can be exercised without real credentials.
 */
function simulatedPayment(decision: Decision): PaymentResult {
  const amount_usd = myrToUsdc(decision.amount_myr);
  const timestamp = new Date().toISOString();
  // Deterministic fake hash so the same invoice always produces the same hash
  const fakeHash =
    "0x" +
    Buffer.from(`sim:${decision.invoice_id}:${timestamp}`)
      .toString("hex")
      .padEnd(64, "0")
      .slice(0, 64);

  console.warn(
    `[PAY][SIM] ${decision.invoice_id} | SIMULATED (no WALLET_PRIVATE_KEY) | ` +
      `${amount_usd} USDC | ${timestamp}`
  );
  return { tx_hash: fakeHash, network: REQUIRED_NETWORK, amount_usd, timestamp };
}

// ── Main export ────────────────────────────────────────────────────────────

/**
 * Pay a clean invoice on Base Sepolia TESTNET using the x402 protocol.
 *
 * Safety invariant: MAINNET IS BLOCKED. The function throws immediately
 * if network is anything other than "base-sepolia".
 *
 * When WALLET_PRIVATE_KEY is absent the function returns a simulated result
 * so the UI/API layer can be tested without real credentials.
 */
export async function pay(decision: Decision): Promise<PaymentResult> {
  // ── Hard mainnet guard (non-negotiable) ───────────────────────────────────
  requireBaseSepolia(REQUIRED_NETWORK);

  const amount_usd = myrToUsdc(decision.amount_myr);
  const timestamp = new Date().toISOString();

  // ── Simulation mode (no credentials) ─────────────────────────────────────
  if (!process.env.WALLET_PRIVATE_KEY) {
    return simulatedPayment(decision);
  }

  try {
    const { client, account } = getTestWalletClient();

    const publicClient = createPublicClient({
      chain: baseSepolia,
      transport: http(),
    });

    // x402 step 1 — encode the USDC transfer call.
    // In a full x402 flow we would first send the request, receive a 402
    // with a payment-details header, then sign and resubmit. Here we send
    // the on-chain payment directly (the upstream service would verify the
    // tx_hash as proof-of-payment).
    const usdcAmount = parseUnits(amount_usd.toFixed(6), 6); // USDC has 6 decimals

    const data = encodeFunctionData({
      abi: ERC20_TRANSFER_ABI,
      functionName: "transfer",
      args: [X402_RECIPIENT, usdcAmount],
    });

    const txHash = await client.sendTransaction({
      account,
      to: USDC_BASE_SEPOLIA,
      data,
      chain: baseSepolia,
    });

    // Wait for the transaction to be included in a block
    await publicClient.waitForTransactionReceipt({ hash: txHash });

    console.log(
      `[PAY] ${decision.invoice_id} | ${txHash} | ${amount_usd} USDC (MOCK FX: 1 MYR = ${MOCK_FX_MYR_TO_USDC} USDC) | ${timestamp}`
    );

    return {
      tx_hash: txHash,
      network: REQUIRED_NETWORK,
      amount_usd,
      timestamp,
    };
  } catch (err) {
    // Re-throw with context so the caller can surface a useful error
    throw new Error(
      `Payment failed for ${decision.invoice_id}: ${err instanceof Error ? err.message : String(err)}`
    );
  }
}
