/**
 * OpenUI Dashboard — entire frontend for the invoice-decision pipeline.
 *
 * Built exclusively with OpenUI primitives defined at the bottom of this
 * file (Badge, Card, Stack, Button, Spinner, Drawer, etc.).
 * No external CSS libraries. No raw HTML nodes outside the primitives.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";

// ── Types (mirrored from server) ───────────────────────────────────────────

interface LineItem {
  description: string;
  qty: number;
  unit_price: number;
}

interface Decision {
  invoice_id: string;
  vendor: string;
  amount_myr: number;
  currency: "MYR";
  decision: "PAY" | "FLAG" | "HUMAN_REVIEW";
  reasons: string[];
  tax_rule_url: string;
  line_items: LineItem[];
}

interface PaymentResult {
  tx_hash: string;
  network: "base-sepolia";
  amount_usd: number;
  timestamp: string;
}

interface PublishResult {
  url: string;
  record_id: string;
}

interface InvoiceRecord {
  decision: Decision;
  status: "processing" | "PAY_QUEUED" | "PAID" | "FLAG" | "HUMAN_REVIEW" | "REJECTED" | "ERROR";
  payment?: PaymentResult;
  publish?: PublishResult;
  error?: string;
}

// ── OpenUI Primitives ──────────────────────────────────────────────────────
// All frontend components are defined here. No raw HTML outside these.

const css = String.raw; // tag for syntax highlighting in editors

const G = {
  bg:         "#0f1117",
  surface:    "#1a1d27",
  surface2:   "#222639",
  border:     "#2e3248",
  text:       "#e2e8f0",
  muted:      "#8892a4",
  primary:    "#6366f1",
  primaryDim: "#312e81",
  green:      "#22c55e",
  greenDim:   "#14532d",
  amber:      "#f59e0b",
  amberDim:   "#78350f",
  red:        "#ef4444",
  redDim:     "#7f1d1d",
  grey:       "#64748b",
  greyDim:    "#1e2535",
  mono:       '"JetBrains Mono","Fira Code",monospace',
};

// Inject global animation keyframes once
function ensureKeyframes() {
  if (document.getElementById("ui-keyframes")) return;
  const s = document.createElement("style");
  s.id = "ui-keyframes";
  s.textContent = css`
    @keyframes ui-spin { to { transform: rotate(360deg); } }
    @keyframes ui-pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    @keyframes ui-fadeIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
  `;
  document.head.appendChild(s);
}
if (typeof document !== "undefined") ensureKeyframes();

// Stack — flex container
interface StackProps extends React.HTMLAttributes<HTMLDivElement> {
  dir?: "row" | "col";
  gap?: number;
  align?: React.CSSProperties["alignItems"];
  justify?: React.CSSProperties["justifyContent"];
  wrap?: boolean;
}
function Stack({ dir = "col", gap = 12, align, justify, wrap, style, children, ...rest }: StackProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: dir === "row" ? "row" : "column",
        gap,
        alignItems: align,
        justifyContent: justify,
        flexWrap: wrap ? "wrap" : undefined,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

// Card
interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  leftBorder?: string; // colour for a 4-px left accent border
}
function Card({ leftBorder, style, children, ...rest }: CardProps) {
  return (
    <div
      style={{
        background: G.surface,
        border: `1px solid ${G.border}`,
        borderRadius: 10,
        padding: "16px 20px",
        borderLeft: leftBorder ? `4px solid ${leftBorder}` : undefined,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

// Badge
type BadgeVariant = "grey" | "green" | "amber" | "red" | "primary" | "outline-amber";
function Badge({ variant = "grey", children }: { variant?: BadgeVariant; children: React.ReactNode }) {
  const map: Record<BadgeVariant, React.CSSProperties> = {
    grey:          { background: G.greyDim,   color: G.grey,  border: `1px solid ${G.grey}33` },
    green:         { background: G.greenDim,  color: G.green, border: `1px solid ${G.green}44` },
    amber:         { background: G.amberDim,  color: G.amber, border: `1px solid ${G.amber}44` },
    red:           { background: G.redDim,    color: G.red,   border: `1px solid ${G.red}44` },
    primary:       { background: G.primaryDim,color: G.primary,border:`1px solid ${G.primary}44` },
    "outline-amber":{ background:"transparent",color: G.amber, border: `1px solid ${G.amber}` },
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        borderRadius: 20,
        fontSize: 11,
        fontWeight: 600,
        whiteSpace: "nowrap",
        ...map[variant],
      }}
    >
      {children}
    </span>
  );
}

// Spinner
function Spinner({ size = 14 }: { size?: number }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        border: `2px solid ${G.border}`,
        borderTop: `2px solid ${G.primary}`,
        borderRadius: "50%",
        animation: "ui-spin .7s linear infinite",
      }}
    />
  );
}

// Button
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "danger" | "ghost";
  loading?: boolean;
  size?: "sm" | "md";
}
function Button({ variant = "primary", loading, size = "md", style, children, disabled, ...rest }: ButtonProps) {
  const base: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: size === "sm" ? "4px 10px" : "7px 16px",
    fontSize: size === "sm" ? 12 : 13,
    fontWeight: 600,
    border: "none",
    borderRadius: 7,
    cursor: disabled || loading ? "not-allowed" : "pointer",
    transition: "opacity .15s, transform .1s",
    opacity: disabled || loading ? 0.6 : 1,
  };
  const map: Record<string, React.CSSProperties> = {
    primary: { background: G.primary,    color: "#fff" },
    danger:  { background: G.red,        color: "#fff" },
    ghost:   { background: G.surface2,   color: G.text, border: `1px solid ${G.border}` },
  };
  return (
    <button style={{ ...base, ...map[variant], ...style }} disabled={disabled || loading} {...rest}>
      {loading && <Spinner size={12} />}
      {children}
    </button>
  );
}

// Text
interface TextProps extends React.HTMLAttributes<HTMLSpanElement> {
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  weight?: "normal" | "medium" | "semibold" | "bold";
  color?: string;
  mono?: boolean;
}
function Text({ size = "md", weight = "normal", color, mono, style, children, ...rest }: TextProps) {
  const sizes: Record<string, number> = { xs: 11, sm: 12, md: 14, lg: 16, xl: 20 };
  const weights: Record<string, number> = { normal: 400, medium: 500, semibold: 600, bold: 700 };
  return (
    <span
      style={{
        fontSize: sizes[size],
        fontWeight: weights[weight],
        color: color ?? G.text,
        fontFamily: mono ? G.mono : undefined,
        ...style,
      }}
      {...rest}
    >
      {children}
    </span>
  );
}

// Divider
function Divider() {
  return <div style={{ height: 1, background: G.border, margin: "4px 0" }} />;
}

// CopyButton — copies text to clipboard with a brief "Copied!" flash
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="sm"
      style={{ padding: "2px 7px", fontSize: 11 }}
      onClick={() => {
        navigator.clipboard.writeText(text).catch(() => {});
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? "✓" : "⎘"}
    </Button>
  );
}

// StatusBadge — maps InvoiceRecord.status to a Badge
function StatusBadge({ status }: { status: InvoiceRecord["status"] }) {
  switch (status) {
    case "processing":
    case "PAY_QUEUED":
      return <Badge variant="grey"><Spinner size={10} /> Processing</Badge>;
    case "PAID":
      return <Badge variant="green">✓ Paid</Badge>;
    case "FLAG":
      return <Badge variant="red">⚑ Flagged</Badge>;
    case "HUMAN_REVIEW":
      return <Badge variant="outline-amber">⚠ Needs Review</Badge>;
    case "REJECTED":
      return <Badge variant="red">✕ Rejected</Badge>;
    case "ERROR":
      return <Badge variant="red">! Error</Badge>;
    default:
      return <Badge variant="grey">{status}</Badge>;
  }
}

// Drawer — collapsible bottom panel
function Drawer({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ border: `1px solid ${G.border}`, borderRadius: 10, overflow: "hidden" }}>
      <button
        style={{
          width: "100%",
          background: G.surface2,
          border: "none",
          padding: "12px 20px",
          color: G.text,
          fontWeight: 600,
          fontSize: 13,
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{title}</span>
        <span style={{ fontSize: 10, color: G.muted }}>{open ? "▲ Collapse" : "▼ Expand"}</span>
      </button>
      {open && (
        <div style={{ background: G.surface, padding: "16px 20px" }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ── Helper formatters ──────────────────────────────────────────────────────

const fmt = new Intl.NumberFormat("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtMyr = (n: number) => `MYR ${fmt.format(n)}`;
const fmtUsd = (n: number) => `$${fmt.format(n)} USDC`;
const shortHash = (h: string) => `${h.slice(0, 8)}…${h.slice(-6)}`;
const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("en-MY", { dateStyle: "short", timeStyle: "short" });

// ── Section A — Invoice List ───────────────────────────────────────────────

function InvoiceTable({
  records,
  onApprove,
  onReject,
  loadingId,
}: {
  records: InvoiceRecord[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  loadingId: string | null;
}) {
  const thStyle: React.CSSProperties = {
    padding: "10px 14px",
    textAlign: "left",
    fontSize: 11,
    fontWeight: 600,
    color: G.muted,
    textTransform: "uppercase",
    letterSpacing: ".05em",
    borderBottom: `1px solid ${G.border}`,
    background: G.surface2,
  };
  const tdStyle: React.CSSProperties = {
    padding: "12px 14px",
    borderBottom: `1px solid ${G.border}`,
    verticalAlign: "middle",
  };

  return (
    <div style={{ overflowX: "auto", borderRadius: 10, border: `1px solid ${G.border}` }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Invoice ID", "Vendor", "Amount (MYR)", "Status", "Actions"].map((h) => (
              <th key={h} style={thStyle}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr
              key={r.decision.invoice_id}
              style={{
                background:
                  r.status === "HUMAN_REVIEW"
                    ? `${G.amber}08`
                    : r.status === "PAID"
                    ? `${G.green}06`
                    : "transparent",
                transition: "background .3s",
              }}
            >
              <td style={tdStyle}>
                <Text size="sm" mono>{r.decision.invoice_id}</Text>
              </td>
              <td style={tdStyle}>
                <Text size="sm">{r.decision.vendor}</Text>
              </td>
              <td style={tdStyle}>
                <Text size="sm" weight="medium">{fmtMyr(r.decision.amount_myr)}</Text>
                {/* MOCK FX tooltip */}
                {r.payment && (
                  <Text size="xs" color={G.muted} style={{ display: "block" }}
                    title="MOCK FX: 1 MYR = 0.22 USDC (testnet only, not a real rate)">
                    ≈ {fmtUsd(r.payment.amount_usd)} *
                  </Text>
                )}
              </td>
              <td style={tdStyle}>
                <StatusBadge status={r.status} />
                {r.error && (
                  <Text size="xs" color={G.red} style={{ display: "block", marginTop: 4 }}>
                    {r.error.slice(0, 60)}
                  </Text>
                )}
              </td>
              <td style={tdStyle}>
                {r.status === "HUMAN_REVIEW" && (
                  <Stack dir="row" gap={6}>
                    <Button
                      variant="primary"
                      size="sm"
                      loading={loadingId === r.decision.invoice_id}
                      onClick={() => onApprove(r.decision.invoice_id)}
                    >
                      Approve
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => onReject(r.decision.invoice_id)}
                    >
                      Reject
                    </Button>
                  </Stack>
                )}
                {r.status === "PAID" && r.payment && (
                  <Text size="xs" color={G.green} mono>
                    {shortHash(r.payment.tx_hash)}
                  </Text>
                )}
              </td>
            </tr>
          ))}
          {records.length === 0 && (
            <tr>
              <td colSpan={5} style={{ ...tdStyle, textAlign: "center", color: G.muted }}>
                No invoices loaded yet…
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Section B — Running Totals ─────────────────────────────────────────────

function TotalsBar({ records }: { records: InvoiceRecord[] }) {
  const paid = records.filter((r) => r.status === "PAID");
  const flagged = records.filter((r) => r.status === "FLAG");
  const review = records.filter((r) => r.status === "HUMAN_REVIEW");
  const totalMyr = paid.reduce((s, r) => s + r.decision.amount_myr, 0);

  const tiles = [
    { label: "Total Processed", value: records.length.toString(),       color: G.primary },
    { label: "Total Paid",       value: fmtMyr(totalMyr),                color: G.green },
    {
      label: "Flagged / Review",
      value: `${flagged.length + review.length} (${flagged.length}F + ${review.length}R)`,
      color: G.amber,
    },
  ];

  return (
    <Stack dir="row" gap={16} wrap>
      {tiles.map((t) => (
        <Card key={t.label} leftBorder={t.color} style={{ flex: "1 1 200px", minWidth: 180 }}>
          <Text size="xs" color={G.muted} style={{ display: "block", marginBottom: 6 }}>
            {t.label}
          </Text>
          <Text size="xl" weight="bold" color={t.color}>
            {t.value}
          </Text>
        </Card>
      ))}
    </Stack>
  );
}

// ── Section C — Human-in-the-Loop Panel ───────────────────────────────────

function HumanReviewPanel({
  records,
  onApprove,
  onReject,
  loadingId,
}: {
  records: InvoiceRecord[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  loadingId: string | null;
}) {
  const pending = records.filter((r) => r.status === "HUMAN_REVIEW");
  if (pending.length === 0) return null;

  return (
    <Stack gap={12}>
      <Stack dir="row" gap={8} align="center">
        <Badge variant="outline-amber">⚠ Human Review Required</Badge>
        <Text size="sm" color={G.muted}>{pending.length} invoice(s) awaiting decision</Text>
      </Stack>

      {pending.map((r) => (
        <Card key={r.decision.invoice_id} leftBorder={G.amber}>
          <Stack gap={12}>
            {/* Header */}
            <Stack dir="row" gap={16} align="center" justify="space-between" wrap>
              <Stack dir="row" gap={12} align="center" wrap>
                <Text size="sm" weight="semibold" mono>{r.decision.invoice_id}</Text>
                <Text size="sm" color={G.muted}>{r.decision.vendor}</Text>
                <Text size="sm" weight="bold">{fmtMyr(r.decision.amount_myr)}</Text>
              </Stack>
              <Stack dir="row" gap={8}>
                <Button
                  variant="primary"
                  loading={loadingId === r.decision.invoice_id}
                  onClick={() => onApprove(r.decision.invoice_id)}
                >
                  ✓ Approve & Pay
                </Button>
                <Button
                  variant="danger"
                  onClick={() => onReject(r.decision.invoice_id)}
                >
                  ✕ Reject
                </Button>
              </Stack>
            </Stack>

            <Divider />

            {/* Reasons */}
            <Stack gap={6}>
              <Text size="xs" color={G.muted} weight="semibold">FLAGS / REASONS</Text>
              <ul style={{ paddingLeft: 18, margin: 0 }}>
                {r.decision.reasons.map((reason, i) => (
                  <li key={i} style={{ color: G.amber, fontSize: 13, marginBottom: 4 }}>
                    {reason}
                  </li>
                ))}
              </ul>
            </Stack>

            {/* Tax-rule source */}
            <Stack dir="row" gap={6} align="center">
              <Text size="xs" color={G.muted}>Tax ruling:</Text>
              <a
                href={r.decision.tax_rule_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: G.primary, fontSize: 12, textDecoration: "none" }}
              >
                {r.decision.tax_rule_url} ↗
              </a>
            </Stack>

            {/* Line items */}
            <details style={{ fontSize: 12 }}>
              <summary style={{ cursor: "pointer", color: G.muted, userSelect: "none" }}>
                Line items ({r.decision.line_items.length})
              </summary>
              <table style={{ width: "100%", marginTop: 8, borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Description", "Qty", "Unit Price", "Subtotal"].map((h) => (
                      <th key={h} style={{ textAlign: "left", color: G.muted, fontWeight: 600, padding: "4px 8px", fontSize: 11 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.decision.line_items.map((li, i) => (
                    <tr key={i}>
                      <td style={{ padding: "4px 8px", color: G.text }}>{li.description}</td>
                      <td style={{ padding: "4px 8px", color: G.muted }}>{li.qty}</td>
                      <td style={{ padding: "4px 8px", color: G.muted }}>{fmtMyr(li.unit_price)}</td>
                      <td style={{ padding: "4px 8px", color: G.text }}>{fmtMyr(li.qty * li.unit_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </Stack>
        </Card>
      ))}
    </Stack>
  );
}

// ── Section D — Transaction Log ────────────────────────────────────────────

function TransactionLog({ records }: { records: InvoiceRecord[] }) {
  const paid = records.filter((r) => r.status === "PAID" && r.payment);

  return (
    <Drawer title={`Transaction Log (${paid.length} paid)`}>
      {paid.length === 0 ? (
        <Text size="sm" color={G.muted}>No completed transactions yet.</Text>
      ) : (
        <Stack gap={8}>
          <Text size="xs" color={G.amber} style={{ display: "block" }}>
            * MOCK FX: 1 MYR = 0.22 USDC — testnet amounts only, not real exchange rates.
          </Text>
          {paid.map((r) => (
            <Card key={r.decision.invoice_id} style={{ padding: "12px 16px" }}>
              <Stack dir="row" gap={16} align="flex-start" wrap>
                {/* Invoice + vendor */}
                <Stack gap={2} style={{ minWidth: 120 }}>
                  <Text size="xs" color={G.muted}>Invoice</Text>
                  <Text size="sm" weight="semibold" mono>{r.decision.invoice_id}</Text>
                  <Text size="xs" color={G.muted}>{r.decision.vendor}</Text>
                </Stack>

                {/* Tx hash */}
                <Stack gap={2} style={{ flex: 1, minWidth: 180 }}>
                  <Text size="xs" color={G.muted}>Tx Hash (Base Sepolia)</Text>
                  <Stack dir="row" gap={4} align="center">
                    <Text size="xs" mono color={G.primary}>{shortHash(r.payment!.tx_hash)}</Text>
                    <CopyButton text={r.payment!.tx_hash} />
                    <a
                      href={`https://sepolia.basescan.org/tx/${r.payment!.tx_hash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: G.primary, fontSize: 11 }}
                    >
                      ↗
                    </a>
                  </Stack>
                </Stack>

                {/* Amount */}
                <Stack gap={2} style={{ minWidth: 100 }}>
                  <Text size="xs" color={G.muted}>Amount</Text>
                  <Text size="sm" weight="medium">{fmtMyr(r.decision.amount_myr)}</Text>
                  {/* MOCK FX label */}
                  <Text size="xs" color={G.muted} title="MOCK FX — not a real rate">
                    ≈ {fmtUsd(r.payment!.amount_usd)} *
                  </Text>
                </Stack>

                {/* cited.md URL */}
                {r.publish && (
                  <Stack gap={2} style={{ minWidth: 150 }}>
                    <Text size="xs" color={G.muted}>cited.md Record</Text>
                    <a
                      href={r.publish.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: G.primary, fontSize: 12, wordBreak: "break-all" }}
                    >
                      {r.publish.url.replace("https://", "")} ↗
                    </a>
                  </Stack>
                )}

                {/* Timestamp */}
                <Stack gap={2} style={{ minWidth: 110 }}>
                  <Text size="xs" color={G.muted}>Timestamp</Text>
                  <Text size="xs" mono>{fmtDate(r.payment!.timestamp)}</Text>
                </Stack>
              </Stack>
            </Card>
          ))}
        </Stack>
      )}
    </Drawer>
  );
}

// ── Root Dashboard ─────────────────────────────────────────────────────────

/** Compact fingerprint — skip React re-render when poll returns identical data */
function snapshotRecords(records: InvoiceRecord[]): string {
  return JSON.stringify(
    records.map((r) => ({
      id: r.decision.invoice_id,
      status: r.status,
      tx: r.payment?.tx_hash ?? null,
      pub: r.publish?.url ?? null,
      err: r.error ?? null,
    }))
  );
}

export default function Dashboard() {
  const [records, setRecords] = useState<InvoiceRecord[]>([]);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [lastPoll, setLastPoll] = useState<Date | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const snapshotRef = useRef("");

  // Poll GET /invoices every 5 seconds — only update state when data changes
  const poll = useCallback(async (force = false) => {
    setFetching(true);
    try {
      const res = await fetch("/invoices");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: InvoiceRecord[] = await res.json();
      const snap = snapshotRecords(data);
      if (force || snap !== snapshotRef.current) {
        snapshotRef.current = snap;
        setRecords(data);
      }
      setLastPoll(new Date());
      setPollError(null);
    } catch (err) {
      setPollError(err instanceof Error ? err.message : String(err));
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    poll(true);
    timerRef.current = setInterval(() => {
      if (document.visibilityState === "visible") poll();
    }, 5000);

    const onVisible = () => {
      if (document.visibilityState === "visible") poll();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [poll]);

  const handleApprove = async (invoiceId: string) => {
    setLoadingId(invoiceId);
    try {
      const res = await fetch(`/invoices/${invoiceId}/approve`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ error: "Unknown error" }));
        throw new Error(body.error ?? `HTTP ${res.status}`);
      }
      await poll(true); // force refresh after approve
    } catch (err) {
      alert(`Approve failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoadingId(null);
    }
  };

  const handleReject = async (invoiceId: string) => {
    try {
      const res = await fetch(`/invoices/${invoiceId}/reject`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ error: "Unknown error" }));
        throw new Error(body.error ?? `HTTP ${res.status}`);
      }
      await poll(true);
    } catch (err) {
      alert(`Reject failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <Stack gap={0} style={{ minHeight: "100vh", background: G.bg }}>
      {/* Nav bar */}
      <div
        style={{
          background: G.surface,
          borderBottom: `1px solid ${G.border}`,
          padding: "0 24px",
          height: 52,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <Stack dir="row" gap={10} align="center">
          <span style={{ fontSize: 18, fontWeight: 800, color: G.primary }}>InvoDecision</span>
          <Badge variant="primary">Base Sepolia Testnet</Badge>
        </Stack>
        <Stack dir="row" gap={8} align="center">
          {pollError ? (
            <Badge variant="red">⚠ Poll error</Badge>
          ) : (
            <Text size="xs" color={G.muted}>
              {lastPoll ? `Updated ${lastPoll.toLocaleTimeString()}` : "Loading…"}
            </Text>
          )}
          {fetching && <Spinner size={10} />}
        </Stack>
      </div>

      {/* Main content */}
      <Stack gap={24} style={{ padding: "24px", maxWidth: 1200, margin: "0 auto", width: "100%" }}>

        {/* Section B — Running Totals */}
        <TotalsBar records={records} />

        {/* Section C — Human-in-the-Loop Panel */}
        <HumanReviewPanel
          records={records}
          onApprove={handleApprove}
          onReject={handleReject}
          loadingId={loadingId}
        />

        {/* Section A — Invoice List */}
        <Stack gap={10}>
          <Stack dir="row" gap={8} align="center" justify="space-between">
            <Text size="md" weight="semibold">All Invoices</Text>
            <Text size="xs" color={G.muted}>Auto-refreshes every 5 s</Text>
          </Stack>
          <InvoiceTable
            records={records}
            onApprove={handleApprove}
            onReject={handleReject}
            loadingId={loadingId}
          />
          <Text size="xs" color={G.muted}>
            * MOCK FX — 1 MYR = 0.22 USDC (testnet only, not a real exchange rate)
          </Text>
        </Stack>

        {/* Section D — Transaction Log */}
        <TransactionLog records={records} />

      </Stack>
    </Stack>
  );
}
