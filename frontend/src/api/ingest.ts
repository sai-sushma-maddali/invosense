import { existsSync, readdirSync, readFileSync } from "fs";
import { resolve } from "path";
import type { Decision, LineItem } from "../actions/pay.js";

/**
 * Ingest the OCR pipeline output (the `out/` directory) and convert each
 * extracted invoice into a {@link Decision} the rest of the app understands.
 *
 * The OCR JSON schema (per file) looks like:
 *   {
 *     invoice_id, company, gst_id?, invoice_no?, date?,
 *     taxable?, tax?, total,
 *     confidence: { field: 0..1 },
 *     overall_confidence: 0..1,
 *     boxes: { field: [x, y, w, h] }
 *   }
 * and is accompanied by an `<invoice_id>_boxes.png` image with the bounding
 * boxes already drawn on it.
 */

interface OcrJson {
  invoice_id: string;
  company: string;
  gst_id?: string;
  invoice_no?: string;
  date?: string;
  taxable?: number;
  tax?: number;
  total: number;
  confidence: Record<string, number>;
  overall_confidence: number;
  boxes: Record<string, number[]>;
}

/** Invoices at/above this MYR value need a human to sign off before paying. */
const AUTO_APPROVE_THRESHOLD_MYR = 100;

/** Per-field confidence below this is surfaced as a review reason. */
const LOW_CONFIDENCE = 0.9;

/** Generic Malaysian tax-ruling reference for GST/SST invoices. */
const DEFAULT_TAX_RULE_URL = "https://mysst.customs.gov.my/";

/** URL prefix under which the server serves the annotated `out/` images. */
const IMAGE_ROUTE = "/invoice-images";

function hasBox(j: OcrJson, field: string): boolean {
  return Array.isArray(j.boxes?.[field]) && j.boxes[field].length === 4;
}

/** Looks like a "SDN BHD" company whose suffix was misread (e.g. "SDN BHU"). */
function companyNameLooksMalformed(company: string): boolean {
  return /\bSDN\s+BH(?!D\b)[A-Z]\b/i.test(company);
}

function buildLineItems(j: OcrJson): LineItem[] {
  const items: LineItem[] = [];
  if (typeof j.taxable === "number") {
    items.push({ description: "Taxable supply (goods/services)", qty: 1, unit_price: j.taxable });
  }
  if (typeof j.tax === "number" && j.tax > 0) {
    items.push({ description: "GST / SST", qty: 1, unit_price: j.tax });
  }
  if (items.length === 0) {
    items.push({ description: "Invoice total", qty: 1, unit_price: j.total });
  }
  return items;
}

/**
 * Derive a decision + human-readable reasons from the OCR fields.
 *
 * Priority: FLAG (data-integrity problems) > HUMAN_REVIEW (missing fields /
 * over threshold) > PAY (clean, complete, under threshold).
 */
function deriveDecision(j: OcrJson): {
  decision: Decision["decision"];
  reasons: string[];
} {
  const flagReasons: string[] = [];
  const reviewReasons: string[] = [];

  // ── Data-integrity problems → FLAG ───────────────────────────────────────
  if (companyNameLooksMalformed(j.company)) {
    flagReasons.push(
      `Company name OCR looks malformed — "${j.company}" (expected "…SDN BHD")`
    );
  }
  if (typeof j.taxable === "number" && typeof j.tax === "number") {
    const computed = Math.round((j.taxable + j.tax) * 100) / 100;
    if (Math.abs(computed - j.total) > 0.01) {
      flagReasons.push(
        `Tax arithmetic mismatch — taxable ${j.taxable} + tax ${j.tax} ≠ total ${j.total}`
      );
    }
  }

  // ── Missing key fields → HUMAN_REVIEW ────────────────────────────────────
  const KEY_FIELDS: Array<[keyof OcrJson | string, string]> = [
    ["gst_id", "GST ID"],
    ["invoice_no", "Invoice number"],
    ["date", "Invoice date"],
  ];
  for (const [field, label] of KEY_FIELDS) {
    if (!hasBox(j, field as string)) {
      reviewReasons.push(`${label} not located on the document (no bounding box)`);
    }
  }

  // ── Amount threshold → HUMAN_REVIEW ──────────────────────────────────────
  if (j.total >= AUTO_APPROVE_THRESHOLD_MYR) {
    reviewReasons.push(
      `Amount RM ${j.total.toFixed(2)} meets the RM ${AUTO_APPROVE_THRESHOLD_MYR} manual-approval threshold`
    );
  }

  // ── Low per-field confidence → surfaced as a review note ──────────────────
  for (const [field, conf] of Object.entries(j.confidence ?? {})) {
    if (conf < LOW_CONFIDENCE) {
      reviewReasons.push(`Low OCR confidence on "${field}" (${Math.round(conf * 100)}%)`);
    }
  }

  if (flagReasons.length > 0) {
    return { decision: "FLAG", reasons: [...flagReasons, ...reviewReasons] };
  }
  if (reviewReasons.length > 0) {
    return { decision: "HUMAN_REVIEW", reasons: reviewReasons };
  }
  return { decision: "PAY", reasons: [] };
}

function toDecision(j: OcrJson): Decision {
  const { decision, reasons } = deriveDecision(j);
  return {
    invoice_id: j.invoice_id,
    vendor: j.company,
    amount_myr: j.total,
    currency: "MYR",
    decision,
    reasons,
    tax_rule_url: DEFAULT_TAX_RULE_URL,
    line_items: buildLineItems(j),
    ocr: {
      company: j.company,
      gst_id: j.gst_id,
      invoice_no: j.invoice_no,
      date: j.date,
      taxable: j.taxable,
      tax: j.tax,
      total: j.total,
      confidence: j.confidence ?? {},
      overall_confidence: j.overall_confidence,
      boxes: j.boxes ?? {},
      image_url: `${IMAGE_ROUTE}/${j.invoice_id}_boxes.png`,
    },
  };
}

/** Resolve the OCR output directory (defaults to the sibling `out/` folder). */
export function resolveOutDir(projectRoot: string): string {
  return resolve(projectRoot, process.env.OUT_DIR ?? "../out");
}

/**
 * Load every `*.json` invoice in the OCR output directory and convert it to a
 * Decision. Returns an empty array if the directory does not exist or has no
 * JSON files (callers can then fall back to the bundled mocks).
 */
export function loadDecisionsFromOut(outDir: string): Decision[] {
  if (!existsSync(outDir)) return [];

  const files = readdirSync(outDir)
    .filter((f) => f.endsWith(".json"))
    .sort();

  const decisions: Decision[] = [];
  for (const file of files) {
    try {
      const raw = readFileSync(resolve(outDir, file), "utf-8");
      const json = JSON.parse(raw) as OcrJson;
      if (!json.invoice_id) {
        console.warn(`[INGEST] Skipping ${file}: missing invoice_id`);
        continue;
      }
      decisions.push(toDecision(json));
    } catch (err) {
      console.error(`[INGEST] Failed to parse ${file}:`, err);
    }
  }
  return decisions;
}
