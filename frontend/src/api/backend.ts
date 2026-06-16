import type { Decision, LineItem } from "../actions/pay.js";
import type { InvoiceRecord, InvoiceStatus } from "./invoices.js";

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8001").replace(/\/$/, "");

const DEFAULT_TAX_RULE_URL = "/tax-rules";

export function resolveSourceUrl(source?: string | null): string {
  if (!source) return DEFAULT_TAX_RULE_URL;
  if (/^https?:\/\//i.test(source)) return source;
  return DEFAULT_TAX_RULE_URL;
}

export interface BackendHealth {
  status: string;
  gmail_watcher: boolean;
  gmail_connected: boolean;
  folder_watcher: boolean;
}

export interface BackendInvoice {
  invoice_id: string;
  source: "gmail" | "upload" | "folder";
  filename: string;
  saved_path: string;
  status: "saved" | "extracting" | "compliance_checking" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  message_id?: string | null;
  extraction?: BackendExtraction | null;
  compliance?: BackendCompliance | null;
  decision?: BackendDecision | null;
  error?: string | null;
}

interface BackendExtraction {
  invoice_id: string;
  company?: string;
  gst_id?: string;
  invoice_no?: string;
  date?: string;
  taxable?: number;
  tax?: number;
  total?: number;
  confidence?: Record<string, number>;
  overall_confidence?: number;
  boxes?: Record<string, number[]>;
  corrected_at?: string;
  correction_count?: number;
}

interface BackendCompliance {
  status: "clean" | "flagged";
  flags?: Array<{
    check: string;
    reason: string;
    message: string;
    source?: string;
  }>;
  notes?: string;
}

interface BackendDecision {
  decision: "auto_approve" | "rejected";
  reason: string;
  compliance_status?: string;
  rejection_reasons?: Array<{
    check: string;
    reason: string;
    message: string;
    source?: string;
  }>;
}

export interface PipelineInfo {
  backend_status: string;
  source: string;
  filename: string;
  message_id?: string | null;
  manually_rerun?: boolean;
  corrected_at?: string;
  correction_count?: number;
  steps: Array<{ name: string; label: string; done: boolean; active: boolean; failed?: boolean }>;
}

function buildLineItems(extraction: BackendExtraction): LineItem[] {
  const items: LineItem[] = [];
  if (typeof extraction.taxable === "number") {
    items.push({
      description: "Taxable supply (goods/services)",
      qty: 1,
      unit_price: extraction.taxable,
    });
  }
  if (typeof extraction.tax === "number" && extraction.tax > 0) {
    items.push({ description: "GST / SST", qty: 1, unit_price: extraction.tax });
  }
  const total = extraction.total ?? 0;
  if (items.length === 0) {
    items.push({ description: "Invoice total", qty: 1, unit_price: total });
  }
  return items;
}

function inboxImageUrl(filename: string): string {
  return `/invoice-images/${encodeURIComponent(filename)}`;
}

function buildPipeline(backend: BackendInvoice): PipelineInfo {
  const order = ["saved", "extracting", "compliance_checking", "completed"] as const;
  const labels: Record<string, string> = {
    saved: "Received",
    extracting: "Extracting",
    compliance_checking: "Compliance",
    completed: "Decision",
  };
  const idx =
    backend.status === "failed"
      ? order.indexOf("compliance_checking")
      : order.indexOf(backend.status as (typeof order)[number]);

  const steps = order.map((name, i) => {
    if (backend.status === "failed") {
      const failAt = order.indexOf("compliance_checking");
      return {
        name,
        label: labels[name],
        done: i < failAt,
        active: false,
        failed: i === failAt,
      };
    }
    return {
      name,
      label: labels[name],
      done: backend.status === "completed" ? true : i < idx,
      active: backend.status !== "completed" && backend.status === name,
      failed: false,
    };
  });

  return {
    backend_status: backend.status,
    source: backend.source,
    filename: backend.filename,
    message_id: backend.message_id,
    manually_rerun: Boolean(backend.extraction?.corrected_at),
    corrected_at: backend.extraction?.corrected_at,
    correction_count: backend.extraction?.correction_count ?? 0,
    steps,
  };
}

function mapBackendDecision(backend: BackendInvoice): {
  decision: Decision["decision"];
  reasons: string[];
  tax_rule_url: string;
} {
  const compliance = backend.compliance;
  const backendDecision = backend.decision;

  const flagReasons =
    compliance?.flags?.map((f) => `${f.check}: ${f.message}`) ??
    backendDecision?.rejection_reasons?.map((r) => `${r.check}: ${r.message}`) ??
    [];

  const tax_rule_url = resolveSourceUrl(
    compliance?.flags?.find((f) => f.source)?.source ??
      backendDecision?.rejection_reasons?.find((r) => r.source)?.source
  );

  if (backend.status !== "completed" && backend.status !== "failed") {
    return { decision: "HUMAN_REVIEW", reasons: ["Pipeline in progress"], tax_rule_url };
  }

  if (backend.status === "failed") {
    return {
      decision: "FLAG",
      reasons: [backend.error ?? "Processing failed"],
      tax_rule_url,
    };
  }

  if (backendDecision?.decision === "auto_approve") {
    return { decision: "PAY", reasons: [], tax_rule_url };
  }

  if (flagReasons.length > 0) {
    return { decision: "FLAG", reasons: flagReasons, tax_rule_url };
  }

  return {
    decision: "HUMAN_REVIEW",
    reasons: [backendDecision?.reason ?? "Rejected — needs review"],
    tax_rule_url,
  };
}

function mapFrontendStatus(
  backend: BackendInvoice,
  aiDecision: Decision["decision"],
  existing?: InvoiceRecord
): InvoiceStatus {
  const backendRejected = backend.decision?.decision === "rejected" || aiDecision === "FLAG";

  if (backendRejected) return "REJECTED";

  if (existing?.status === "PAID" && existing.payment && aiDecision === "PAY") {
    return "PAID";
  }

  if (backend.status === "failed") return "ERROR";
  if (backend.status !== "completed") return "processing";

  if (aiDecision === "PAY") return existing?.payment ? "PAID" : "PAY_QUEUED";
  return "HUMAN_REVIEW";
}

export function mapBackendToFrontend(
  backend: BackendInvoice,
  existing?: InvoiceRecord
): InvoiceRecord {
  const extraction = backend.extraction;
  const { decision: aiDecision, reasons, tax_rule_url } = mapBackendDecision(backend);

  const vendor =
    extraction?.company ?? backend.filename.replace(/\.[^.]+$/, "").replace(/_/g, " ");
  const amount_myr = extraction?.total ?? 0;

  const inboxName = backend.saved_path.split("/").pop() ?? backend.filename;

  const decision: Decision = {
    invoice_id: backend.invoice_id,
    vendor,
    amount_myr,
    currency: "MYR",
    decision: aiDecision,
    reasons,
    tax_rule_url,
    line_items: extraction ? buildLineItems(extraction) : [],
    ocr: extraction
      ? {
          company: extraction.company ?? vendor,
          gst_id: extraction.gst_id,
          invoice_no: extraction.invoice_no,
          date: extraction.date,
          taxable: extraction.taxable,
          tax: extraction.tax,
          total: extraction.total ?? amount_myr,
          confidence: extraction.confidence ?? {},
          overall_confidence: extraction.overall_confidence ?? 0,
          boxes: extraction.boxes ?? {},
          image_url: inboxImageUrl(inboxName),
        }
      : undefined,
  };

  const status = mapFrontendStatus(backend, aiDecision, existing);
  const backendRejected =
    backend.decision?.decision === "rejected" || aiDecision === "FLAG";

  return {
    decision,
    status,
    payment: backendRejected ? undefined : existing?.payment,
    publish: backendRejected ? undefined : existing?.publish,
    error: backend.error ?? existing?.error,
    pipeline: buildPipeline(backend),
    compliance: backend.compliance ?? undefined,
    backend_decision: backend.decision?.decision,
  };
}

export async function fetchBackendHealth(): Promise<BackendHealth | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/health`);
    if (!res.ok) return null;
    return (await res.json()) as BackendHealth;
  } catch {
    return null;
  }
}

export async function fetchBackendInvoices(): Promise<BackendInvoice[]> {
  const res = await fetch(`${BACKEND_URL}/invoices`);
  if (!res.ok) {
    throw new Error(`Backend /invoices returned HTTP ${res.status}`);
  }
  const data = (await res.json()) as { invoices?: BackendInvoice[] };
  return data.invoices ?? [];
}

export async function retryBackendInvoice(invoiceId: string): Promise<BackendInvoice> {
  const res = await fetch(`${BACKEND_URL}/invoices/${invoiceId}/retry`, { method: "POST" });
  const data = (await res.json()) as BackendInvoice & { error?: string };
  if (!res.ok || data.error) {
    throw new Error(data.error ?? `Retry failed HTTP ${res.status}`);
  }
  return data;
}

export interface ExtractionCorrectionPayload {
  company?: string;
  gst_id?: string;
  invoice_no?: string;
  date?: string;
  taxable?: number;
  tax?: number;
  total?: number;
  refresh_boxes?: boolean;
}

export async function correctBackendExtraction(
  invoiceId: string,
  fields: ExtractionCorrectionPayload
): Promise<BackendInvoice> {
  const res = await fetch(`${BACKEND_URL}/invoices/${invoiceId}/extraction`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  const data = (await res.json()) as BackendInvoice & { error?: string; message?: string };
  if (!res.ok || data.error) {
    throw new Error(data.message ?? data.error ?? `Correction failed HTTP ${res.status}`);
  }
  return data;
}

export function getBackendUrl(): string {
  return BACKEND_URL;
}
