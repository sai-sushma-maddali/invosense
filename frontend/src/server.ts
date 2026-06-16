import "dotenv/config";
import express from "express";
import cors from "cors";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";
import {
  loadDecisions,
  getAllInvoices,
  approveInvoice,
  rejectInvoice,
  retryInvoice,
  correctInvoiceExtraction,
  setUseBackend,
} from "./api/invoices.js";
import { loadDecisionsFromOut, resolveOutDir } from "./api/ingest.js";
import { fetchBackendHealth, getBackendUrl } from "./api/backend.js";
import type { Decision } from "./actions/pay.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const OUT_DIR = resolveOutDir(ROOT);
const INBOX_DIR = resolve(ROOT, "../data/inbox");
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8001";

function loadMockDecisions(): Decision[] {
  try {
    const raw = readFileSync(resolve(ROOT, "mocks/decisions.json"), "utf-8");
    return JSON.parse(raw) as Decision[];
  } catch (err) {
    console.error("[SERVER] Could not load mocks/decisions.json:", err);
    return [];
  }
}

function bootstrapDecisions(): { source: string; decisions: Decision[] } {
  const fromOut = loadDecisionsFromOut(OUT_DIR);
  if (fromOut.length > 0) {
    return { source: `OCR output (${OUT_DIR})`, decisions: fromOut };
  }
  return { source: "mocks/decisions.json", decisions: loadMockDecisions() };
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function tryBackendMode(): Promise<boolean> {
  for (let attempt = 1; attempt <= 10; attempt++) {
    try {
      const health = await fetchBackendHealth();
      if (health?.status === "ok") {
        setUseBackend(true);
        console.log(`[SERVER] Connected to FastAPI backend at ${getBackendUrl()}`);
        console.log(
          `[SERVER] Gmail watcher: ${health.gmail_watcher} | connected: ${health.gmail_connected}`
        );
        return true;
      }
    } catch {
      // retry until backend is up
    }
    if (attempt < 10) {
      await sleep(1000);
    }
  }
  setUseBackend(false);
  const { source, decisions } = bootstrapDecisions();
  loadDecisions(decisions);
  console.warn(`[SERVER] Backend unavailable — using ${source}`);
  return false;
}

const app = express();

app.use(cors());
app.use(express.json());
app.use(express.static(resolve(ROOT, "public")));
app.use("/invoice-images", express.static(INBOX_DIR));
app.use("/invoice-images-legacy", express.static(OUT_DIR));

app.get("/health", async (_req, res) => {
  const backend = await fetchBackendHealth();
  res.json({
    frontend: "ok",
    backend_url: getBackendUrl(),
    backend_connected: Boolean(backend),
    gmail_watcher: backend?.gmail_watcher ?? false,
    gmail_connected: backend?.gmail_connected ?? false,
    folder_watcher: backend?.folder_watcher ?? false,
  });
});

app.get("/invoices", async (_req, res) => {
  try {
    res.json(await getAllInvoices());
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(502).json({ error: message });
  }
});

app.post("/invoices/:id/approve", async (req, res) => {
  try {
    res.json(await approveInvoice(req.params.id));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(400).json({ error: message });
  }
});

app.post("/invoices/:id/reject", (req, res) => {
  try {
    res.json(rejectInvoice(req.params.id));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(400).json({ error: message });
  }
});

app.post("/invoices/:id/retry", async (req, res) => {
  try {
    res.json(await retryInvoice(req.params.id));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(400).json({ error: message });
  }
});

app.patch("/invoices/:id/extraction", async (req, res) => {
  try {
    res.json(await correctInvoiceExtraction(req.params.id, req.body ?? {}));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(400).json({ error: message });
  }
});

app.get("/tax-rules", async (_req, res) => {
  try {
    const upstream = await fetch(`${BACKEND_URL}/compliance/tax-rules`);
    const text = await upstream.text();
    if (!upstream.ok) {
      res.status(upstream.status).type("text/plain").send(text);
      return;
    }
    res.type("text/markdown; charset=utf-8").send(text);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(502).type("text/plain").send(message);
  }
});

app.get("*", (_req, res) => {
  res.sendFile(resolve(ROOT, "public/index.html"));
});

const PORT = parseInt(process.env.PORT ?? "3000", 10);

tryBackendMode().then((backendMode) => {
  app.listen(PORT, () => {
    console.log(`[SERVER] InvoSense UI listening on http://localhost:${PORT}`);
    console.log(`[SERVER] Backend URL: ${BACKEND_URL} (${backendMode ? "live" : "offline"})`);
    console.log(`[SERVER] Serving inbox images from ${INBOX_DIR}`);
    console.log(`[SERVER] API: GET /health  GET /invoices  GET /tax-rules  POST /invoices/:id/approve|reject|retry  PATCH /invoices/:id/extraction`);
  });
});
