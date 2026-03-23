import { useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2,
  GitCompare,
  Shield,
  Brain,
  Cpu,
  Copy,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  Info,
  CheckCircle2,
  MinusCircle,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { API } from "@/App";
 
const SnapshotCard = ({ title, icon, data, rawPreview, highlight }) => {
  if (!data) return null;
 
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          {icon}
          <div>
            <h3 className="font-semibold text-gray-900">{title}</h3>
            <p className="text-xs text-gray-500">Model snapshot</p>
          </div>
        </div>
 
        {highlight && (
          <span className="text-xs bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-semibold">
            Impacted
          </span>
        )}
      </div>
 
      <div className="flex flex-wrap gap-2 mb-4">
        <span className="text-xs px-2 py-1 rounded-full border bg-gray-100 text-gray-700 border-gray-200">
          Verdict: {data?.verdict || "—"}
        </span>
        <span className="text-xs px-2 py-1 rounded-full border bg-gray-100 text-gray-700 border-gray-200">
          Confidence: {data?.confidence_band || "—"}
        </span>
        <span className="text-xs px-2 py-1 rounded-full border bg-gray-100 text-gray-700 border-gray-200">
          Risk: {data?.narrative_risk || "—"}
        </span>
        <span className="text-xs px-2 py-1 rounded-full border bg-gray-100 text-gray-700 border-gray-200">
          Policy: {data?.sharing_policy || "—"}
        </span>
        <span className="text-xs px-2 py-1 rounded-full border bg-gray-100 text-gray-700 border-gray-200">
          Tone: {data?.tone_mode || "—"}
        </span>
      </div>
 
      <div className="mb-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide">Safe User Response</p>
        <p className="text-sm text-gray-700 mt-2">
          {data?.safe_user_response || "—"}
        </p>
      </div>
 
      <div className="grid gap-4">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide">Risk Signals</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(data?.risk_signals || []).length ? (
              data.risk_signals.map((item, i) => (
                <span
                  key={`${item}-${i}`}
                  className="text-xs px-2 py-1 rounded-md bg-gray-100 text-gray-700 border border-gray-200"
                >
                  {item}
                </span>
              ))
            ) : (
              <p className="text-sm text-gray-500 italic">None</p>
            )}
          </div>
        </div>
 
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide">Verification Needed</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(data?.verification_needed || []).length ? (
              data.verification_needed.map((item, i) => (
                <span
                  key={`${item}-${i}`}
                  className="text-xs px-2 py-1 rounded-md bg-gray-100 text-gray-700 border border-gray-200"
                >
                  {item}
                </span>
              ))
            ) : (
              <p className="text-sm text-gray-500 italic">None</p>
            )}
          </div>
        </div>
      </div>
 
      {rawPreview ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-gray-600">Raw Output</summary>
          <pre className="mt-2 p-3 rounded-md bg-gray-50 border text-xs text-gray-700 overflow-auto max-h-56 whitespace-pre-wrap break-words">
            {rawPreview}
          </pre>
        </details>
      ) : null}
    </div>
  );
};
/* --------------------------
   Utilities
   --------------------------*/
 
const cn = (...classes) => classes.filter(Boolean).join(" ");
 
const formatLabel = (value = "") =>
  String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
 
const displayValue = (value, fallback = "—") => {
  if (value === null || value === undefined || value === "") return fallback;
  return typeof value === "string" ? formatLabel(value) : String(value);
};
 
const copyToClipboard = async (text) => {
  try {
    if (!text) return false;
 
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
 
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  } catch {
    return false;
  }
};
 
const normalizeList = (items) => (Array.isArray(items) ? items.filter(Boolean) : []);
 
const listDiff = (base = [], lora = []) => {
  const b = new Set(normalizeList(base));
  const l = new Set(normalizeList(lora));
  return {
    added: [...l].filter((x) => !b.has(x)),
    removed: [...b].filter((x) => !l.has(x)),
    shared: [...l].filter((x) => b.has(x)),
  };
};
 
const changed = (a, b) => JSON.stringify(a ?? null) !== JSON.stringify(b ?? null);
 
const getVerdictBadge = (value) => {
  if (value === "likely_true") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (value === "likely_false") return "bg-red-50 text-red-700 border-red-200";
  if (value === "uncertain") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};
 
const getPolicyBadge = (value) => {
  if (value === "allow") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (value === "do_not_share") return "bg-red-50 text-red-700 border-red-200";
  if (value === "caution") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};
 
const getRiskBadge = (value) => {
  if (value === "low") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (value === "medium") return "bg-amber-50 text-amber-700 border-amber-200";
  if (value === "high") return "bg-red-50 text-red-700 border-red-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};
 
const getToneBadge = (value) => {
  if (value === "harden") return "bg-red-50 text-red-700 border-red-200";
  if (value === "soften") return "bg-blue-50 text-blue-700 border-blue-200";
  if (value === "neutral") return "bg-gray-100 text-gray-700 border-gray-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};
 
const getConfidenceBadge = (value) => {
  if (value === "high") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (value === "medium") return "bg-amber-50 text-amber-700 border-amber-200";
  if (value === "low") return "bg-red-50 text-red-700 border-red-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};
 
const badgeForField = (field, value) => {
  if (field === "verdict") return getVerdictBadge(value);
  if (field === "sharing_policy") return getPolicyBadge(value);
  if (field === "narrative_risk") return getRiskBadge(value);
  if (field === "tone_mode") return getToneBadge(value);
  if (field === "confidence_band") return getConfidenceBadge(value);
  return "bg-gray-100 text-gray-700 border-gray-200";
};
 
/* --------------------------
   Tiny UI primitives
   --------------------------*/
 
const Pill = ({ children, className = "" }) => (
  <span className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold", className)}>
    {children}
  </span>
);
 
const SectionLabel = ({ children }) => (
  <p className="text-[11px] text-gray-500 uppercase tracking-wide">{children}</p>
);
 
const HoverInfo = ({ label, content }) => {
  const [open, setOpen] = useState(false);
  if (!content) return null;
 
  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
      >
        <Info className="w-3.5 h-3.5" />
        {label}
      </button>
 
      {open && (
        <div className="absolute z-20 mt-2 w-80 rounded-lg border border-gray-200 bg-white p-3 shadow-lg text-xs text-gray-700 right-0">
          {Array.isArray(content) ? (
            <div className="flex flex-wrap gap-2">
              {content.length ? content.map((item, i) => (
                <span
                  key={`${item}-${i}`}
                  className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1"
                >
                  {formatLabel(item)}
                </span>
              )) : <span className="italic text-gray-500">None</span>}
            </div>
          ) : (
            <div className="whitespace-pre-wrap break-words">{content}</div>
          )}
        </div>
      )}
    </div>
  );
};
 
const ChipList = ({ items = [], emptyText = "None" }) => {
  if (!items || items.length === 0) {
    return <p className="text-sm text-gray-500 italic">{emptyText}</p>;
  }
 
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item, i) => (
        <span
          key={`${item}-${i}`}
          className="text-xs px-2 py-1 rounded-md bg-gray-100 text-gray-700 border border-gray-200 break-all"
        >
          {formatLabel(item)}
        </span>
      ))}
    </div>
  );
};
 
const CollapsibleBlock = ({ title, text }) => {
  const [open, setOpen] = useState(false);
  if (!text) return null;
 
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between gap-3">
        <SectionLabel>{title}</SectionLabel>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => copyToClipboard(text)}
            className="bg-gray-50 text-gray-700 border hover:bg-gray-100"
            size="sm"
          >
            <Copy className="w-4 h-4 mr-2" />
            Copy
          </Button>
          <Button
            onClick={() => setOpen((s) => !s)}
            className="bg-white text-gray-700 border hover:bg-gray-50"
            size="sm"
          >
            {open ? (
              <>
                <ChevronUp className="w-4 h-4 mr-2" />
                Hide
              </>
            ) : (
              <>
                <ChevronDown className="w-4 h-4 mr-2" />
                View
              </>
            )}
          </Button>
        </div>
      </div>
 
      {open && (
        <pre className="mt-3 p-3 rounded-md bg-gray-50 border text-xs text-gray-700 overflow-auto max-h-56 whitespace-pre-wrap break-words">
          {text}
        </pre>
      )}
    </div>
  );
};
 
/* --------------------------
   Top impact strip
   --------------------------*/
 
const TopImpactStrip = ({ metrics, baseResult, loraResult }) => {
  if (!metrics) return null;
 
  const phase1 = metrics.phase1_behavior || {};
  const signalDelta = (metrics.signal_counts?.added_by_lora || []).length;
  const verificationDelta = (metrics.verification_counts?.added_by_lora || []).length;
 
  return (
    <div className="sticky top-0 z-10 rounded-xl border border-blue-100 bg-white/95 backdrop-blur p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#0033A0]" />
            <h3 className="font-semibold text-[#0033A0]">LoRA Impact Summary</h3>
          </div>
          <p className="text-sm text-gray-600 mt-1">
            Focused view of how the LoRA changed the guardrail outcome.
          </p>
        </div>
 
        <HoverInfo
          label="Why this matters"
          content={metrics.improvement_reasons || []}
        />
      </div>
 
      <div className="mt-4 flex flex-wrap gap-2">
        <Pill className={metrics.verdict_changed ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {metrics.verdict_changed ? <Sparkles className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          Verdict {metrics.verdict_changed ? "Changed" : "Same"}
        </Pill>
 
        <Pill className={metrics.sharing_policy_changed ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {metrics.sharing_policy_changed ? <Sparkles className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          Policy {metrics.sharing_policy_changed ? "Changed" : "Same"}
        </Pill>
 
        <Pill className={metrics.tone_changed ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {metrics.tone_changed ? <Sparkles className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          Tone {metrics.tone_changed ? "Changed" : "Same"}
        </Pill>
 
        <Pill className={verificationDelta > 0 ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {verificationDelta > 0 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          +{verificationDelta} Verification
        </Pill>
 
        <Pill className={signalDelta > 0 ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {signalDelta > 0 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          +{signalDelta} Signals
        </Pill>
 
        <Pill className={phase1.lora_authority_verification_present ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {phase1.lora_authority_verification_present ? <CheckCircle2 className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          Authority Guidance
        </Pill>
 
        <Pill className={phase1.lora_boundary_language_present ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {phase1.lora_boundary_language_present ? <CheckCircle2 className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          Boundary Language
        </Pill>
 
        <Pill className={phase1.lora_sensitive_rumor_hardening ? "bg-red-50 text-red-700 border-red-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
          {phase1.lora_sensitive_rumor_hardening ? <AlertTriangle className="w-3.5 h-3.5" /> : <MinusCircle className="w-3.5 h-3.5" />}
          Rumor Hardening
        </Pill>
      </div>
    </div>
  );
};
 
/* --------------------------
   Compact comparison table
   --------------------------*/
 
const TableBadge = ({ field, value }) => (
  <span className={cn("inline-flex rounded-full border px-2 py-1 text-xs font-semibold", badgeForField(field, value))}>
    {displayValue(value)}
  </span>
);
 
const CompactComparisonTable = ({ baseResult, loraResult, metrics }) => {
  if (!baseResult || !loraResult || !metrics) return null;
 
  const rows = [
    { key: "verdict", label: "Verdict", changed: metrics.verdict_changed },
    { key: "confidence_band", label: "Confidence", changed: metrics.confidence_band_changed },
    { key: "narrative_risk", label: "Risk", changed: metrics.risk_changed },
    { key: "sharing_policy", label: "Policy", changed: metrics.sharing_policy_changed },
    { key: "tone_mode", label: "Tone", changed: metrics.tone_changed },
    { key: "safe_user_response", label: "User Response", changed: changed(baseResult.safe_user_response, loraResult.safe_user_response) },
  ];
 
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitCompare className="w-4 h-4 text-[#0033A0]" />
          <h3 className="font-semibold text-gray-900">Base vs LoRA</h3>
        </div>
        <HoverInfo
          label="Hover details"
          content="Hover chips in the lower panels to inspect exactly what LoRA added or changed."
        />
      </div>
 
      <div className="grid grid-cols-12 text-xs uppercase tracking-wide text-gray-500 bg-gray-50 border-b border-gray-100">
        <div className="col-span-3 px-4 py-2">Field</div>
        <div className="col-span-3 px-4 py-2">Base</div>
        <div className="col-span-1 px-2 py-2 text-center"></div>
        <div className="col-span-3 px-4 py-2">LoRA</div>
        <div className="col-span-2 px-4 py-2">Impact</div>
      </div>
 
      {rows.map((row) => (
        <div
          key={row.key}
          className={cn(
            "grid grid-cols-12 items-center border-b border-gray-100 last:border-b-0",
            row.changed ? "bg-blue-50/40" : "bg-white"
          )}
        >
          <div className="col-span-3 px-4 py-3 text-sm font-medium text-gray-800">
            {row.label}
          </div>
 
          <div className="col-span-3 px-4 py-3 text-sm text-gray-700">
            {row.key === "safe_user_response" ? (
              <span className="line-clamp-2">{baseResult[row.key] || "—"}</span>
            ) : (
              <TableBadge field={row.key} value={baseResult[row.key]} />
            )}
          </div>
 
          <div className="col-span-1 px-2 py-3 text-center text-gray-400">
            <ArrowRight className="w-4 h-4 inline" />
          </div>
 
          <div className="col-span-3 px-4 py-3 text-sm text-gray-700">
            {row.key === "safe_user_response" ? (
              <span className="line-clamp-2">{loraResult[row.key] || "—"}</span>
            ) : (
              <TableBadge field={row.key} value={loraResult[row.key]} />
            )}
          </div>
 
          <div className="col-span-2 px-4 py-3">
            <span
              className={cn(
                "text-xs font-semibold",
                row.changed ? "text-blue-700" : "text-gray-400"
              )}
            >
              {row.changed ? "Changed" : "Same"}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};
 
/* --------------------------
   Tabbed details panel
   --------------------------*/
 
const TabButton = ({ active, onClick, children }) => (
  <button
    onClick={onClick}
    className={cn(
      "px-3 py-2 text-sm rounded-lg border transition",
      active
        ? "bg-[#0033A0] text-white border-[#0033A0]"
        : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
    )}
  >
    {children}
  </button>
);
 
const TabbedDetailPanel = ({ baseResult, loraResult, metrics, sourcePrecheck, normalizedContent, baseRaw, loraRaw }) => {
  const [tab, setTab] = useState("impact");
 
  if (!metrics) return null;
 
  const signalDiff = listDiff(baseResult?.risk_signals || [], loraResult?.risk_signals || []);
  const verificationDiff = listDiff(baseResult?.verification_needed || [], loraResult?.verification_needed || []);
  const phase1 = metrics.phase1_behavior || {};
 
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
      <div className="flex flex-wrap gap-2 mb-4">
        <TabButton active={tab === "impact"} onClick={() => setTab("impact")}>Impact</TabButton>
        <TabButton active={tab === "signals"} onClick={() => setTab("signals")}>Signals</TabButton>
        <TabButton active={tab === "verification"} onClick={() => setTab("verification")}>Verification</TabButton>
        <TabButton active={tab === "source"} onClick={() => setTab("source")}>Source</TabButton>
        <TabButton active={tab === "raw"} onClick={() => setTab("raw")}>Raw</TabButton>
      </div>
 
      {tab === "impact" && (
        <div className="grid md:grid-cols-2 gap-4">
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Operational Effect</SectionLabel>
            <div className="mt-3 flex flex-wrap gap-2">
              <Pill className={phase1.lora_authority_verification_present ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
                Authority Guidance: {phase1.lora_authority_verification_present ? "Yes" : "No"}
              </Pill>
              <Pill className={phase1.lora_boundary_language_present ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
                Boundary Language: {phase1.lora_boundary_language_present ? "Yes" : "No"}
              </Pill>
              <Pill className={phase1.lora_sensitive_rumor_hardening ? "bg-red-50 text-red-700 border-red-200" : "bg-gray-50 text-gray-600 border-gray-200"}>
                Rumor Hardening: {phase1.lora_sensitive_rumor_hardening ? "Yes" : "No"}
              </Pill>
            </div>
          </div>
 
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Improvement Reasons</SectionLabel>
            <div className="mt-3">
              <ChipList
                items={metrics.improvement_reasons || []}
                emptyText="No clear LoRA improvement detected."
              />
            </div>
          </div>
 
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 md:col-span-2">
            <SectionLabel>Safe Response Change</SectionLabel>
            <div className="grid md:grid-cols-2 gap-4 mt-3">
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-1">Base</p>
                <p className="text-sm text-gray-700">{baseResult?.safe_user_response || "—"}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-blue-700 mb-1">LoRA</p>
                <p className="text-sm text-gray-900">{loraResult?.safe_user_response || "—"}</p>
              </div>
            </div>
          </div>
        </div>
      )}
 
      {tab === "signals" && (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Added By LoRA</SectionLabel>
            <div className="mt-3">
              <ChipList items={signalDiff.added} emptyText="No additional risk signals." />
            </div>
          </div>
 
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Removed From Base</SectionLabel>
            <div className="mt-3">
              <ChipList items={signalDiff.removed} emptyText="Nothing removed." />
            </div>
          </div>
 
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Shared Signals</SectionLabel>
            <div className="mt-3">
              <ChipList items={signalDiff.shared} emptyText="No shared signals." />
            </div>
          </div>
        </div>
      )}
 
      {tab === "verification" && (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Added By LoRA</SectionLabel>
            <div className="mt-3">
              <ChipList items={verificationDiff.added} emptyText="No additional verification guidance." />
            </div>
          </div>
 
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Removed From Base</SectionLabel>
            <div className="mt-3">
              <ChipList items={verificationDiff.removed} emptyText="Nothing removed." />
            </div>
          </div>
 
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Shared Guidance</SectionLabel>
            <div className="mt-3">
              <ChipList items={verificationDiff.shared} emptyText="No shared verification guidance." />
            </div>
          </div>
        </div>
      )}
 
      {tab === "source" && (
        <div className="grid md:grid-cols-2 gap-4">
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Source Snapshot</SectionLabel>
            <div className="mt-3 flex flex-wrap gap-2">
              <Pill className="bg-gray-100 text-gray-700 border-gray-200">
                Present: {sourcePrecheck?.source_present ? "Yes" : "No"}
              </Pill>
              <Pill className="bg-gray-100 text-gray-700 border-gray-200">
                Type: {displayValue(sourcePrecheck?.source_type)}
              </Pill>
              <Pill className="bg-gray-100 text-gray-700 border-gray-200">
                Tier: {displayValue(sourcePrecheck?.source_tier)}
              </Pill>
            </div>
            <div className="mt-4 text-sm text-gray-700 space-y-2">
              <div><span className="font-medium">Domain:</span> {sourcePrecheck?.source_domain || "None"}</div>
              <div><span className="font-medium">URL:</span> {sourcePrecheck?.source_url || "None"}</div>
            </div>
            <div className="mt-4">
              <SectionLabel>Flags</SectionLabel>
              <div className="mt-2">
                <ChipList items={sourcePrecheck?.url_flags || []} emptyText="No URL flags." />
              </div>
            </div>
          </div>
 
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Normalized Input</SectionLabel>
            <pre className="mt-3 text-xs text-gray-700 whitespace-pre-wrap break-words max-h-72 overflow-auto">
              {normalizedContent || "—"}
            </pre>
          </div>
        </div>
      )}
 
      {tab === "raw" && (
        <div className="grid md:grid-cols-2 gap-4">
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>Base Raw</SectionLabel>
            <CollapsibleBlock title="Base Output" text={baseRaw} />
          </div>
          <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
            <SectionLabel>LoRA Raw</SectionLabel>
            <CollapsibleBlock title="LoRA Output" text={loraRaw} />
          </div>
        </div>
      )}
    </div>
  );
};
 
/* --------------------------
   Main page
   --------------------------*/
 
export default function AnalysisPage() {
  const [input, setInput] = useState("");
  const [compareMode, setCompareMode] = useState(true);
  const [loading, setLoading] = useState(false);
 
  const [baseResult, setBaseResult] = useState(null);
  const [loraResult, setLoraResult] = useState(null);
  const [comparisonMetrics, setComparisonMetrics] = useState(null);
  const [sourcePrecheck, setSourcePrecheck] = useState(null);
  const [normalizedContent, setNormalizedContent] = useState("");
 
  const [baseRaw, setBaseRaw] = useState("");
  const [loraRaw, setLoraRaw] = useState("");
  const [error, setError] = useState("");
 
  const analyze = async () => {
    if (!input.trim()) return;
 
    setError("");
    setLoading(true);
 
    setBaseResult(null);
    setLoraResult(null);
    setComparisonMetrics(null);
    setSourcePrecheck(null);
    setNormalizedContent("");
    setBaseRaw("");
    setLoraRaw("");
 
    try {
      const { data } = await axios.post(`${API}/compare`, {
        content: input,
      });
 
      setBaseResult(data.base_output || null);
      setLoraResult(data.lora_output || null);
      setComparisonMetrics(data.comparison_metrics || null);
      setSourcePrecheck(data.source_precheck || null);
      setNormalizedContent(data.normalized_content || "");
      setBaseRaw(data.base_raw || "");
      setLoraRaw(data.lora_raw || "");
    } catch (err) {
      console.error(err);
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Unexpected API error — check console"
      );
    } finally {
      setLoading(false);
    }
  };
 
  const singleViewData =
    loraResult && Object.keys(loraResult).length > 0 ? loraResult : baseResult;
  const singleViewRaw = loraRaw || baseRaw;
 
  return (
    <div className="bg-[#F7F9FC] min-h-screen text-gray-900">
      <div className="bg-white border-b border-gray-200 px-6 lg:px-10 py-4 flex justify-between items-center">
        <div className="flex items-center gap-4">
          <Shield className="w-8 h-8 text-[#0033A0]" />
          <div>
            <p className="text-xs uppercase tracking-widest text-gray-400">
              NTT DATA
            </p>
            <h1 className="text-lg font-semibold text-[#0033A0]">
              Information Integrity Platform
            </h1>
          </div>
        </div>
 
        <div className="text-sm text-gray-500">LoRA Impact Demo</div>
      </div>
 
      <div className="max-w-7xl mx-auto px-6 lg:px-10 py-6 space-y-6">
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="grid lg:grid-cols-[1fr_260px] gap-4">
            <div>
              <Textarea
                placeholder="Paste a headline, article snippet, internal rumor, or claim..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="min-h-[120px] border-gray-300"
              />
 
              <div className="flex items-center justify-between mt-4 gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                  <Switch checked={compareMode} onCheckedChange={setCompareMode} />
                  <span className="text-sm text-gray-600 flex items-center gap-2">
                    <GitCompare className="w-4 h-4" />
                    Focus on LoRA impact
                  </span>
                </div>
 
                <div className="flex items-center gap-2">
                  <Button
                    onClick={() => {
                      setInput("");
                      setBaseResult(null);
                      setLoraResult(null);
                      setComparisonMetrics(null);
                      setSourcePrecheck(null);
                      setNormalizedContent("");
                      setBaseRaw("");
                      setLoraRaw("");
                      setError("");
                    }}
                    className="bg-white border text-gray-700 hover:bg-gray-50"
                  >
                    Clear
                  </Button>
 
                  <Button
                    onClick={analyze}
                    disabled={loading || !input.trim()}
                    className="bg-[#0033A0] hover:bg-[#002080] text-white"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Analysing
                      </>
                    ) : (
                      "Analyse"
                    )}
                  </Button>
                </div>
              </div>
 
              {error && (
                <p className="mt-4 text-sm text-red-600 font-medium">{error}</p>
              )}
            </div>
 
            <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 text-xs text-gray-700">
              <p className="font-semibold text-gray-800 mb-2">This layout is optimized for:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Immediate LoRA impact visibility</li>
                <li>Minimal scrolling</li>
                <li>Hover-access to secondary detail</li>
              </ul>
            </div>
          </div>
        </div>
 
        {compareMode && comparisonMetrics && (
          <TopImpactStrip
            metrics={comparisonMetrics}
            baseResult={baseResult}
            loraResult={loraResult}
          />
        )}
 
        {compareMode ? (
          comparisonMetrics && (
            <div className="grid xl:grid-cols-[1.2fr_1fr] gap-6">
              <div className="space-y-6">
                <CompactComparisonTable
                  baseResult={baseResult}
                  loraResult={loraResult}
                  metrics={comparisonMetrics}
                />
                <TabbedDetailPanel
                  baseResult={baseResult}
                  loraResult={loraResult}
                  metrics={comparisonMetrics}
                  sourcePrecheck={sourcePrecheck}
                  normalizedContent={normalizedContent}
                  baseRaw={baseRaw}
                  loraRaw={loraRaw}
                />
              </div>
 
              <div className="space-y-6">
                <SnapshotCard
                  title="Base Model"
                  icon={<Cpu className="w-5 h-5 text-gray-500" />}
                  data={baseResult}
                  rawPreview={baseRaw}
                  highlight={false}
                />
 
                <SnapshotCard
                  title="LoRA Guardrail Model"
                  icon={<Brain className="w-5 h-5 text-[#0033A0]" />}
                  data={loraResult}
                  rawPreview={loraRaw}
                  highlight={Boolean(comparisonMetrics?.improved)}
                />
              </div>
            </div>
          )
        ) : (
          <div className="grid xl:grid-cols-[1.2fr_1fr] gap-6">
            <div>
              <SnapshotCard
                title="Selected Output"
                icon={<Brain className="w-5 h-5 text-[#0033A0]" />}
                data={singleViewData}
                rawPreview={singleViewRaw}
                highlight={false}
              />
            </div>
 
            <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
              <SectionLabel>Source / Input</SectionLabel>
              <div className="mt-4">
                <ChipList items={sourcePrecheck?.url_flags || []} emptyText="No URL flags." />
              </div>
              <CollapsibleBlock title="Normalized Input" text={normalizedContent} />
            </div>
          </div>
        )}
 
        <div className="text-center text-xs text-gray-400">
          © 2026 NTT DATA — Information Integrity Intelligence Platform
        </div>
      </div>
    </div>
  );
}
 