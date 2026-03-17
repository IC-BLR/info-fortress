import { useState } from "react";
import axios from "axios";
import {
  Loader2,
  GitCompare,
  ShieldCheck,
  Shield,
  Brain,
  Cpu,
  Copy,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { API } from "@/App";
 
/* --------------------------
   Small utility components
   --------------------------*/
 
const Badge = ({ children, className = "" }) => (
  <span
    className={
      "text-xs px-2 py-1 rounded-full font-semibold inline-block " + className
    }
  >
    {children}
  </span>
);
 
const copyToClipboard = async (text) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    } else {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      return true;
    }
  } catch {
    return false;
  }
};
 
/* --------------------------
   Result Card (Light Enterprise)
   --------------------------*/
 
const IndicatorList = ({ indicators = [] }) => {
  if (!indicators || indicators.length === 0)
    return <p className="text-sm text-gray-500">No indicators found.</p>;
 
  return (
    <div className="space-y-3">
      {indicators.map((ind, i) => (
        <div
          key={`${ind.name}-${i}`}
          className="border border-gray-100 rounded-md p-3 bg-gray-50"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-gray-800">{ind.name}</p>
              {ind.evidence && (
                <p className="text-xs text-gray-600 mt-1 break-words">
                  <span className="text-gray-500">Evidence: </span>
                  <span className="italic">"{ind.evidence}"</span>
                </p>
              )}
            </div>
            <Badge
              className={`${
                ind.severity === "high"
                  ? "bg-red-50 text-red-600"
                  : ind.severity === "med" || ind.severity === "medium"
                  ? "bg-amber-50 text-amber-600"
                  : "bg-emerald-50 text-emerald-600"
              } border`}
            >
              {ind.severity ? ind.severity.toUpperCase() : "LOW"}
            </Badge>
          </div>
        </div>
      ))}
    </div>
  );
};
 
const ResultCard = ({ title, icon, data, highlight, rawPreview }) => {
  const [openRaw, setOpenRaw] = useState(false);
  if (!data) return null;
 
  const riskColor = (score) => {
    if (score >= 70) return "text-red-600";
    if (score >= 40) return "text-amber-600";
    return "text-emerald-600";
  };
 
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-3">
          {icon}
          <div>
            <h3 className="font-semibold text-gray-900">{title}</h3>
            <p className="text-xs text-gray-500">Model output snapshot</p>
          </div>
        </div>
 
        <div className="flex items-center gap-3">
          {highlight && (
            <span className="text-xs bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-semibold">
              Improved
            </span>
          )}
          <Badge className="bg-gray-100 text-gray-700 border">
            {data.article_type || "unknown"}
          </Badge>
        </div>
      </div>
 
      <div className="grid grid-cols-2 gap-6 mb-5">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide">
            Manipulation Signal Score
          </p>
          <p className={`text-3xl font-bold ${riskColor(data.risk_score || 0)}`}>
            {(typeof data.risk_score === "number" ? data.risk_score : String(data.risk_score || "")).toString()}
          </p>
        </div>
 
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide">
            Confidence
          </p>
          <p className="text-3xl font-bold text-gray-900">
            {Math.round((data.confidence || 0) * 100)}%
          </p>
        </div>
      </div>
 
      <div className="mb-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide">Summary</p>
        <p className="text-sm text-gray-700 mt-2">
          {data.summary || "No summary provided by model."}
        </p>
      </div>
 
      <div className="mb-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide">Indicators</p>
        <div className="mt-3">
          <IndicatorList indicators={data.indicators || []} />
        </div>
      </div>
 
      {/* raw toggle */}
      {rawPreview && (
        <div className="mt-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Raw</p>
            <div className="flex items-center gap-2">
              <Button
                onClick={() => {
                  copyToClipboard(rawPreview).then((ok) => {
                    // ideally show toast; here simple alert (non-blocking)
                    if (ok) {
                      /* eslint-disable no-alert */
                      // small unobtrusive fallback
                    }
                  });
                }}
                className="bg-gray-50 text-gray-700 border hover:bg-gray-100"
                size="sm"
              >
                <Copy className="w-4 h-4 mr-2" />
                Copy raw
              </Button>
 
              <Button
                onClick={() => setOpenRaw((s) => !s)}
                className="bg-white text-gray-700 border hover:bg-gray-50"
                size="sm"
              >
                {openRaw ? (
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
 
          {openRaw && (
            <pre className="mt-3 p-3 rounded-md bg-gray-50 border text-xs text-gray-700 overflow-auto max-h-44">
              {rawPreview}
            </pre>
          )}
        </div>
      )}
    </div>
  );
};
 
/* --------------------------
   Comparison Metrics Panel
   --------------------------*/
 
const ComparisonPanel = ({ metrics }) => {
  if (!metrics) return null;
 
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
      <h4 className="text-sm font-semibold text-gray-800 mb-4">
        Comparison Metrics
      </h4>
 
      <div className="grid grid-cols-2 gap-4 mb-3">
        <div>
          <p className="text-xs text-gray-500 uppercase">Risk (Base → LoRA)</p>
          <p className="text-lg font-bold">
            {metrics.base_risk} → {metrics.lora_risk}{" "}
            <span
              className={
                metrics.risk_delta < 0 ? "text-emerald-600" : "text-red-600"
              }
            >
              ({metrics.risk_delta > 0 ? "+" : ""}
              {metrics.risk_delta})
            </span>
          </p>
        </div>
 
        <div>
          <p className="text-xs text-gray-500 uppercase">Confidence Δ</p>
          <p className="text-lg font-bold">
            {(metrics.base_confidence * 100).toFixed(1)}% →{" "}
            {(metrics.lora_confidence * 100).toFixed(1)}%{" "}
            <span
              className={metrics.confidence_delta > 0 ? "text-emerald-600" : "text-red-600"}
            >
              ({metrics.confidence_delta > 0 ? "+" : ""}
              {metrics.confidence_delta.toFixed(3)})
            </span>
          </p>
        </div>
      </div>
 
      <div className="mb-3">
        <p className="text-xs text-gray-500 uppercase">Indicator counts</p>
        <p className="text-sm text-gray-700 mt-1">
          Base: {metrics.indicator_counts.base_count} — LoRA: {metrics.indicator_counts.lora_count} — Shared:{" "}
          {metrics.indicator_counts.shared_indicator_count}
        </p>
      </div>
 
      <div className="mb-3">
        <p className="text-xs text-gray-500 uppercase">New indicators (LoRA)</p>
        <ul className="list-disc list-inside text-sm text-gray-700 mt-2">
          {(metrics.indicator_counts.new_indicators || []).slice(0, 6).map((n, i) => (
            <li key={i} className="break-words">
              {n}
            </li>
          ))}
          {(!metrics.indicator_counts.new_indicators ||
            metrics.indicator_counts.new_indicators.length === 0) && (
            <li className="text-gray-500">No new indicators</li>
          )}
        </ul>
      </div>
 
      <div className="mb-2">
        <p className="text-xs text-gray-500 uppercase">Improved?</p>
        <p className="text-sm font-semibold text-gray-800">
          {metrics.improved ? "Yes" : "No"}
        </p>
        <p className="text-xs text-gray-500 mt-2">
          {metrics.improvement_reasons?.slice(0, 3).join(" • ") || ""}
        </p>
      </div>
    </div>
  );
};
 
/* --------------------------
   Main Page
   --------------------------*/
 
export default function AnalyzePage() {
  const [input, setInput] = useState("");
  const [compareMode, setCompareMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [baseResult, setBaseResult] = useState(null);
  const [loraResult, setLoraResult] = useState(null);
  const [comparisonMetrics, setComparisonMetrics] = useState(null);
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
    setBaseRaw("");
    setLoraRaw("");
 
    try {
      const { data } = await axios.post(`${API}/compare`, {
        content: input,
      });
 
      setBaseResult(data.base_output || null);
      setLoraResult(data.lora_output || null);
      setComparisonMetrics(data.comparison_metrics || null);
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
 
  const improved =
    comparisonMetrics?.improved ||
    (baseResult && loraResult && loraResult.risk_score !== baseResult.risk_score);
 
  return (
    <div className="bg-[#F7F9FC] min-h-screen text-gray-900">
      {/* NAV */}
      <div className="bg-white border-b border-gray-200 px-10 py-4 flex justify-between items-center">
        {/* <div className="flex items-center gap-4">
          <Shield className="w-8 h-8 text-[#0033A0]" />
          <div>
            <p className="text-xs uppercase tracking-widest text-gray-400">
              NTT DATA
            </p>
            <h1 className="text-lg font-semibold text-[#0033A0]">
              Information Integrity Platform
            </h1>
          </div>
        </div> */}
        <div className="flex items-center gap-4">
          {/* NTT DATA Logo */}
          <img
            src="./logo.png"
            alt="NTT DATA Logo"
            className="w-12 h-12 object-contain"
          />

          <div>
            <h1 className="text-lg font-semibold text-[#0033A0]">
              Info fortress
            </h1>
          </div>
        </div>
 
        <div className="text-sm text-gray-500">Context Intelligence Demo</div>
      </div>
 
      {/* INPUT */}
      <div className="max-w-6xl mx-auto px-10 py-8">
        <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
          <div className="flex items-start gap-6">
            <div className="flex-1">
              <Textarea
                placeholder="Paste headline, article snippet, or claim..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="min-h-[140px] border-gray-300"
              />
              <div className="flex items-center justify-between mt-4">
                <div className="flex items-center gap-3">
                  <Switch checked={compareMode} onCheckedChange={setCompareMode} />
                  <span className="text-sm text-gray-600 flex items-center gap-2">
                    <GitCompare className="w-4 h-4" />
                    Compare Base vs LoRA
                  </span>
                </div>
 
                <div className="flex items-center gap-2">
                  <Button
                    onClick={() => {
                      setInput("");
                      setBaseResult(null);
                      setLoraResult(null);
                      setComparisonMetrics(null);
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
            </div>
 
            <div className="w-64 hidden md:block">
              <div className="bg-gray-50 border border-gray-100 rounded-md p-4 text-xs text-gray-700">
                <p className="font-semibold text-gray-800 mb-2">Demo tips</p>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Paste single-claim headlines for fastest results</li>
                  <li>Try toggling Compare to see LoRA differences</li>
                  <li>Use official sources in input to get authority attribution</li>
                </ul>
              </div>
            </div>
          </div>
 
          {error && (
            <p className="mt-4 text-sm text-red-600 font-medium">{error}</p>
          )}
        </div>
      </div>
 
      {/* RESULTS */}
      <div className="max-w-6xl mx-auto px-10 pb-16 grid gap-8">
        {/* Metrics + cards */}
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 grid lg:grid-cols-2 gap-6">
            <ResultCard
              title="Base Model"
              icon={<Cpu className="w-5 h-5 text-gray-500" />}
              data={baseResult}
              rawPreview={baseRaw}
              highlight={false}
            />
 
            <ResultCard
              title="LoRA Enhanced Model"
              icon={<Brain className="w-5 h-5 text-[#0033A0]" />}
              data={loraResult}
              rawPreview={loraRaw}
              highlight={improved}
            />
          </div>
 
          <div>
            <ComparisonPanel metrics={comparisonMetrics} />
            {/* Improvement banner */}
            {improved && (
              <div className="mt-6 bg-blue-50 border border-blue-100 rounded-lg p-4 flex items-start gap-3">
                <ShieldCheck className="w-6 h-6 text-[#0033A0]" />
                <div>
                  <p className="font-semibold text-[#0033A0]">LoRA Contextual Calibration</p>
                  <p className="text-sm text-gray-600">
                    LoRA refined model behavior detected. See comparison metrics for details.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
 
        {/* Footer */}
        <div className="text-center text-xs text-gray-400">
          © 2026 NTT DATA — Information Integrity Intelligence Platform
        </div>
      </div>
    </div>
  );
}