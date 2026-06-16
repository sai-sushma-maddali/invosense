import { pay } from "../actions/pay.js";
import { publish } from "../actions/publish.js";
import type { Decision, PaymentResult } from "../actions/pay.js";
import type { PublishResult } from "../actions/publish.js";
import {
  fetchBackendInvoices,
  fetchBackendHealth,
  mapBackendToFrontend,
  retryBackendInvoice,
  correctBackendExtraction,
  type PipelineInfo,
  type ExtractionCorrectionPayload,
} from "./backend.js";

export type InvoiceStatus =
  | "processing"
  | "PAY_QUEUED"
  | "PAID"
  | "FLAG"
  | "HUMAN_REVIEW"
  | "REJECTED"
  | "ERROR";

export interface InvoiceRecord {
  decision: Decision;
  status: InvoiceStatus;
  payment?: PaymentResult;
  publish?: PublishResult;
  error?: string;
  pipeline?: PipelineInfo;
  compliance?: {
    status: string;
    flags?: Array<{ check: string; reason: string; message: string; source?: string }>;
    notes?: string;
  };
  backend_decision?: "auto_approve" | "rejected";
}

const store = new Map<string, InvoiceRecord>();
const payInFlight = new Set<string>();
let useBackend = true;

export function loadDecisions(decisions: Decision[]): void {
  for (const d of decisions) {
    const initial: InvoiceStatus =
      d.decision === "PAY" ? "PAY_QUEUED" : d.decision === "FLAG" ? "FLAG" : "HUMAN_REVIEW";
    store.set(d.invoice_id, { decision: d, status: initial });
    if (d.decision === "PAY") {
      setImmediate(() => processPay(d.invoice_id));
    }
  }
  console.log(`[INVOICES] Loaded ${decisions.length} decisions into store`);
}

export function setUseBackend(enabled: boolean): void {
  useBackend = enabled;
}

export async function syncFromBackend(): Promise<void> {
  if (!useBackend) {
    try {
      const health = await fetchBackendHealth();
      if (health?.status === "ok") {
        setUseBackend(true);
        console.log("[INVOICES] Backend came online — switching to live sync");
      } else {
        return;
      }
    } catch {
      return;
    }
  }

  const backendInvoices = await fetchBackendInvoices();
  const seen = new Set<string>();
  for (const backend of backendInvoices) {
    seen.add(backend.invoice_id);
    const existing = store.get(backend.invoice_id);
    const mapped = mapBackendToFrontend(backend, existing);
    store.set(backend.invoice_id, mapped);
    if (shouldAutoPay(mapped, existing)) {
      queueAutoPay(backend.invoice_id);
    }
  }
  for (const id of [...store.keys()]) {
    if (!seen.has(id)) {
      store.delete(id);
    }
  }
}

function shouldAutoPay(record: InvoiceRecord, previous?: InvoiceRecord): boolean {
  // After rejection or manual review, require explicit Approve — do not auto-pay on re-sync.
  if (previous && ["REJECTED", "HUMAN_REVIEW", "FLAG", "ERROR"].includes(previous.status)) {
    return false;
  }
  return (
    record.backend_decision === "auto_approve" &&
    record.decision.decision === "PAY" &&
    record.pipeline?.backend_status === "completed" &&
    !record.payment &&
    record.status !== "ERROR" &&
    record.status !== "REJECTED"
  );
}

function queueAutoPay(invoiceId: string): void {
  if (payInFlight.has(invoiceId)) return;
  payInFlight.add(invoiceId);
  setImmediate(() => processPay(invoiceId).finally(() => payInFlight.delete(invoiceId)));
}

async function processPay(invoiceId: string): Promise<void> {
  const record = store.get(invoiceId);
  if (!record || record.payment) return;

  store.set(invoiceId, { ...record, status: "processing" });

  try {
    const payment = await pay(record.decision);
    const pub = await publish(record.decision, payment);
    store.set(invoiceId, { ...record, status: "PAID", payment, publish: pub });
    console.log(`[INVOICES] Auto X402 payment → PAID: ${invoiceId}`);
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    store.set(invoiceId, { ...record, status: "ERROR", error });
    console.error(`[INVOICES] PAY failed for ${invoiceId}: ${error}`);
  }
}

export async function getAllInvoices(): Promise<InvoiceRecord[]> {
  if (useBackend) {
    await syncFromBackend();
  }
  return Array.from(store.values());
}

export async function approveInvoice(invoiceId: string): Promise<InvoiceRecord> {
  const record = store.get(invoiceId);
  if (!record) throw new Error(`Invoice "${invoiceId}" not found`);
  if (record.status !== "HUMAN_REVIEW") {
    throw new Error(`Invoice "${invoiceId}" is in status "${record.status}", expected "HUMAN_REVIEW"`);
  }

  store.set(invoiceId, { ...record, status: "processing" });

  try {
    const payment = await pay(record.decision);
    const pub = await publish(record.decision, payment);
    const updated: InvoiceRecord = { ...record, status: "PAID", payment, publish: pub };
    store.set(invoiceId, updated);
    return updated;
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    store.set(invoiceId, { ...record, status: "ERROR", error });
    throw new Error(`Approval failed for ${invoiceId}: ${error}`);
  }
}

export function rejectInvoice(invoiceId: string): InvoiceRecord {
  const record = store.get(invoiceId);
  if (!record) throw new Error(`Invoice "${invoiceId}" not found`);
  if (record.status !== "HUMAN_REVIEW") {
    throw new Error(`Invoice "${invoiceId}" is in status "${record.status}", expected "HUMAN_REVIEW"`);
  }
  const updated: InvoiceRecord = { ...record, status: "REJECTED" };
  store.set(invoiceId, updated);
  return updated;
}

export async function retryInvoice(invoiceId: string): Promise<InvoiceRecord> {
  if (!useBackend) throw new Error("Retry requires a connected backend");
  const backend = await retryBackendInvoice(invoiceId);
  const existing = store.get(invoiceId);
  const mapped = mapBackendToFrontend(backend, existing);
  store.set(invoiceId, mapped);
  if (shouldAutoPay(mapped)) queueAutoPay(invoiceId);
  return mapped;
}

export async function correctInvoiceExtraction(
  invoiceId: string,
  fields: ExtractionCorrectionPayload
): Promise<InvoiceRecord> {
  if (!useBackend) throw new Error("Correction requires a connected backend");
  const backend = await correctBackendExtraction(invoiceId, fields);
  const existing = store.get(invoiceId);
  const mapped = mapBackendToFrontend(backend, existing);
  store.set(invoiceId, mapped);
  if (shouldAutoPay(mapped)) queueAutoPay(invoiceId);
  return mapped;
}
