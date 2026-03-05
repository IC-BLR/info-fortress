import { useState } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  FileText,
  Globe,
  Loader2,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Sparkles,
  Link,
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  BookOpen,
  AlertCircle,
  Eye,
  BarChart2,
  Hash,
} from "lucide-react";
import { toast } from "sonner";
import { API } from "@/App";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ─── helpers ────────────────────────────────────────────────────────────────

/** Safely parse a risk score that might arrive as string or number */
const toNum = (v) => {
  const n = parseFloat(v);
  return isNaN(n) ? 0 : n;
};

const fmtScore = (v) => toNum(v).toFixed(1);

/** Turn snake_case into "Snake Case" */
const pretty = (s) =>
  (s || "unknown").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const riskColor = (score) => {
  const n = toNum(score);
  if (n >= 70) return "text-red-500";
  if (n >= 40) return "text-amber-500";
  return "text-emerald-500";
};

const riskBg = (score) => {
  const n = toNum(score);
  if (n >= 70) return "bg-red-500/10 border-red-500/30";
  if (n >= 40) return "bg-amber-500/10 border-amber-500/30";
  return "bg-emerald-500/10 border-emerald-500/30";
};

const veracityColor = (v) => {
  if (!v) return "text-zinc-400";
  const val = v.toLowerCase();
  if (val === "verified" || val === "likely_true") return "text-emerald-500";
  if (val === "false" || val === "likely_false") return "text-red-500";
  if (val === "blocked") return "text-red-600";
  return "text-amber-500";
};

const actionColor = (a) => {
  if (!a) return "text-zinc-400";
  const v = a.toLowerCase();
  if (v === "trust") return "text-emerald-500";
  if (v === "flag" || v === "do_not_share" || v === "urgent_response") return "text-red-500";
  if (v === "caution" || v === "monitor") return "text-amber-500";
  return "text-blue-400";
};

const actionBg = (a) => {
  if (!a) return "bg-zinc-800/50 border-zinc-700";
  const v = a.toLowerCase();
  if (v === "trust") return "bg-emerald-500/10 border-emerald-500/20";
  if (v === "flag" || v === "do_not_share" || v === "urgent_response")
    return "bg-red-500/10 border-red-500/20";
  if (v === "caution" || v === "monitor") return "bg-amber-500/10 border-amber-500/20";
  return "bg-blue-500/10 border-blue-500/20";
};

// ─── small reusable chips ────────────────────────────────────────────────────

const Chip = ({ label, value, color = "text-zinc-300" }) => (
  <div className="p-3 bg-zinc-800/50 rounded-sm">
    <p className="text-xs text-zinc-500 mb-1 uppercase tracking-wide">{label}</p>
    <p className={`text-sm font-semibold ${color}`}>{value || "—"}</p>
  </div>
);

const TagList = ({ title, items, icon: Icon, iconColor, bg, border }) => {
  if (!items || items.length === 0) return null;
  // Filter out template placeholders the LLM sometimes echoes back
  const clean = items.filter(
    (i) => i && !i.startsWith("<") && !i.startsWith("ONLY") && i.trim().length > 2
  );
  if (clean.length === 0) return null;
  return (
    <div className={`p-4 rounded-sm border ${bg} ${border}`}>
      <h4 className={`text-sm font-semibold mb-2 flex items-center gap-2 ${iconColor}`}>
        {Icon && <Icon className="w-4 h-4" />}
        {title}
      </h4>
      <ul className="space-y-1">
        {clean.map((item, i) => (
          <li key={i} className="text-sm text-zinc-300 flex items-start gap-2">
            <span className={`mt-1 flex-shrink-0 ${iconColor}`}>•</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
};

const SectionHeader = ({ children }) => (
  <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
    <Sparkles className="w-4 h-4 text-violet-500" />
    {children}
  </h4>
);

// ─── Sourcing quality badge ──────────────────────────────────────────────────
const SourcingBadge = ({ sq }) => {
  if (!sq) return null;
  const { named_sources, anonymous_sources, documents_cited, expert_quotes, assessment } = sq;
  return (
    <div className="p-4 bg-zinc-800/30 rounded-sm">
      <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <BookOpen className="w-4 h-4 text-blue-400" />
        Sourcing Quality
        {assessment && (
          <span
            className={`ml-auto text-xs px-2 py-0.5 rounded-full uppercase font-bold ${
              assessment === "well-sourced"
                ? "bg-emerald-500/20 text-emerald-400"
                : assessment === "adequately-sourced"
                ? "bg-blue-500/20 text-blue-400"
                : assessment === "poorly-sourced"
                ? "bg-amber-500/20 text-amber-400"
                : "bg-red-500/20 text-red-400"
            }`}
          >
            {assessment}
          </span>
        )}
      </h4>
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: "Named", val: named_sources },
          { label: "Anon", val: anonymous_sources },
          { label: "Docs", val: documents_cited },
          { label: "Experts", val: expert_quotes },
        ].map(({ label, val }) => (
          <div key={label} className="text-center p-2 bg-zinc-800/50 rounded-sm">
            <p className="text-lg font-bold font-mono text-white">{val ?? "?"}</p>
            <p className="text-xs text-zinc-500">{label}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Claims breakdown ────────────────────────────────────────────────────────
const ClaimsBreakdown = ({ claims }) => {
  if (!claims || claims.length === 0) return null;
  const colorMap = {
    verified: "text-emerald-400",
    plausible: "text-blue-400",
    unverified: "text-amber-400",
    false: "text-red-500",
    misleading: "text-red-400",
  };
  return (
    <div className="p-4 bg-zinc-800/30 rounded-sm">
      <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <BarChart2 className="w-4 h-4 text-violet-400" />
        Claims Breakdown
      </h4>
      <ul className="space-y-2">
        {claims.map((c, i) => (
          <li key={i} className="border-l-2 border-zinc-700 pl-3">
            <p className="text-sm text-zinc-200">{c.claim}</p>
            <div className="flex items-center gap-2 mt-1">
              <span
                className={`text-xs font-bold uppercase ${
                  colorMap[c.assessment?.toLowerCase()] || "text-zinc-400"
                }`}
              >
                {pretty(c.assessment)}
              </span>
              {c.concern && c.concern !== "null" && (
                <span className="text-xs text-zinc-500">— {c.concern}</span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

// ─── Extracted URL notice ────────────────────────────────────────────────────
const ExtractedUrlBanner = ({ analysis }) => {
  if (analysis.input_type !== "url_extracted_from_claim") return null;
  return (
    <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-sm flex items-start gap-3">
      <ExternalLink className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
      <div>
        <p className="text-xs text-blue-400 font-semibold uppercase">
          URL detected — article fetched &amp; analysed
        </p>
        <p className="text-xs text-zinc-400 mt-0.5 break-all">{analysis.extracted_url}</p>
      </div>
    </div>
  );
};

// ─── Guardrails block notice ─────────────────────────────────────────────────
const GuardrailsBlock = ({ violation }) => {
  if (!violation) return null;
  return (
    <div className="p-4 bg-red-900/30 border border-red-500/40 rounded-sm">
      <h4 className="text-sm font-bold text-red-400 mb-1 flex items-center gap-2">
        <AlertCircle className="w-4 h-4" />
        Blocked by Llama Guard
      </h4>
      <p className="text-xs text-zinc-400">{violation.message}</p>
      {violation.category_labels?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {violation.category_labels.map((l, i) => (
            <span key={i} className="text-xs bg-red-500/20 text-red-300 px-2 py-0.5 rounded-full">
              {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Empty / loading states ──────────────────────────────────────────────────
const EmptyState = ({ icon: Icon, text }) => (
  <div className="h-64 flex items-center justify-center text-zinc-500 text-sm">
    <div className="text-center">
      <Icon className="w-8 h-8 mx-auto mb-2 text-zinc-600" />
      <p>{text}</p>
    </div>
  </div>
);

const LoadingState = ({ text = "Analysing…" }) => (
  <div className="h-64 flex items-center justify-center">
    <div className="text-center">
      <Loader2 className="w-8 h-8 mx-auto mb-2 text-violet-500 animate-spin" />
      <p className="text-zinc-500">{text}</p>
    </div>
  </div>
);

// ════════════════════════════════════════════════════════════════════════════
// URL / Claim result panel
// Backend keys for URL path:   risk_score, veracity_assessment, article_type,
//   source_credibility, headline_accuracy, sourcing_quality{}, claims[],
//   manipulation_indicators[], emotional_language[], missing_context[],
//   strengths[], concerns[], fact_check_priorities[], summary,
//   recommended_action, article_title, article_author, article_published,
//   source_domain, is_credible_source, word_count
//
// Backend keys for claim path: risk_score, veracity_assessment, claim_type,
//   manipulation_tactics[], emotional_triggers[], red_flags[],
//   legitimate_elements[], missing_context[], fact_check_suggestion,
//   potential_harm, summary, recommended_action
//   + when URL extracted: input_type, extracted_url, original_claim
// ════════════════════════════════════════════════════════════════════════════

const UrlAnalysisResult = ({ data }) => {
  const isUrlClaim = !!data.extracted_url || !!data.article_title;

  // Claim path uses manipulation_tactics; URL path uses manipulation_indicators
  const manipIndicators =
    data.manipulation_indicators ||
    data.manipulation_tactics ||
    [];

  // Claim path uses emotional_triggers; URL path uses emotional_language
  const emotionalItems =
    data.emotional_language ||
    data.emotional_triggers ||
    [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4"
    >
      {/* URL-extracted banner */}
      <ExtractedUrlBanner analysis={data} />

      {/* Guardrails block */}
      {data.guardrails_blocked && <GuardrailsBlock violation={data.guard_violation} />}

      {/* Source credibility */}
      {(data.source_domain || data.is_credible_source !== undefined) && (
        <div
          className={`p-3 rounded-sm border flex items-center gap-3 ${
            data.is_credible_source
              ? "bg-emerald-500/10 border-emerald-500/20"
              : "bg-amber-500/10 border-amber-500/20"
          }`}
        >
          {data.is_credible_source ? (
            <ShieldCheck className="w-5 h-5 text-emerald-500 flex-shrink-0" />
          ) : (
            <ShieldAlert className="w-5 h-5 text-amber-500 flex-shrink-0Messages" />
          )}
          <div>
            <p
              className={`text-sm font-semibold ${
                data.is_credible_source ? "text-emerald-500" : "text-amber-500"
              }`}
            >
              {data.is_credible_source ? "Verified Credible Source" : "Unverified Source"}
            </p>
            <p className="text-xs text-zinc-400">{data.source_domain}</p>
          </div>
        </div>
      )}

      {/* Article meta */}
      {data.article_title && (
        <div className="p-3 bg-zinc-800/50 rounded-sm space-y-1">
          <p className="text-xs text-zinc-500 uppercase">Article</p>
          <p className="text-sm text-white font-medium">{data.article_title}</p>
          <div className="flex flex-wrap gap-3 mt-1">
            {data.article_author && (
              <span className="text-xs text-zinc-400">By {data.article_author}</span>
            )}
            {data.article_published && (
              <span className="text-xs text-zinc-400">{data.article_published}</span>
            )}
            {data.word_count > 0 && (
              <span className="text-xs text-zinc-500">{data.word_count} words extracted</span>
            )}
          </div>
        </div>
      )}

      {/* Score row */}
      <div className={`grid gap-3 ${isUrlClaim ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-2"}`}>
        <div className={`p-3 rounded-sm border ${riskBg(data.risk_score)}`}>
          <p className="text-xs text-zinc-500 mb-1 uppercase">Risk Score</p>
          <p className={`text-3xl font-bold font-mono ${riskColor(data.risk_score)}`}>
            {fmtScore(data.risk_score)}
          </p>
        </div>
        <div className="p-3 bg-zinc-800/50 rounded-sm">
          <p className="text-xs text-zinc-500 mb-1 uppercase">Veracity</p>
          <p className={`text-lg font-bold uppercase ${veracityColor(data.veracity_assessment)}`}>
            {pretty(data.veracity_assessment)}
          </p>
        </div>
        {data.article_type && (
          <div className="p-3 bg-zinc-800/50 rounded-sm">
            <p className="text-xs text-zinc-500 mb-1 uppercase">Type</p>
            <p className="text-sm font-semibold text-zinc-200">
              {pretty(data.article_type)}
            </p>
          </div>
        )}
        {data.claim_type && (
          <div className="p-3 bg-zinc-800/50 rounded-sm">
            <p className="text-xs text-zinc-500 mb-1 uppercase">Claim Type</p>
            <p className="text-sm font-semibold text-zinc-200">{pretty(data.claim_type)}</p>
          </div>
        )}
      </div>

      {/* Recommended action */}
      <div className={`p-3 rounded-sm border ${actionBg(data.recommended_action)}`}>
        <p className="text-xs text-zinc-500 mb-1 uppercase">Recommended Action</p>
        <p className={`text-xl font-bold uppercase ${actionColor(data.recommended_action)}`}>
          {pretty(data.recommended_action)}
        </p>
      </div>

      {/* Headline accuracy + source credibility row */}
      {(data.headline_accuracy || data.source_credibility || data.potential_harm) && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {data.headline_accuracy && (
            <Chip
              label="Headline"
              value={pretty(data.headline_accuracy)}
              color={
                data.headline_accuracy === "accurate"
                  ? "text-emerald-400"
                  : data.headline_accuracy === "misleading" || data.headline_accuracy === "fabricated"
                  ? "text-red-400"
                  : "text-amber-400"
              }
            />
          )}
          {data.source_credibility && (
            <Chip
              label="Src Credibility"
              value={pretty(data.source_credibility)}
              color={
                data.source_credibility === "high"
                  ? "text-emerald-400"
                  : data.source_credibility === "low"
                  ? "text-red-400"
                  : "text-amber-400"
              }
            />
          )}
          {data.potential_harm && (
            <Chip
              label="Potential Harm"
              value={data.potential_harm}
              color={
                data.potential_harm?.toLowerCase().startsWith("low")
                  ? "text-emerald-400"
                  : data.potential_harm?.toLowerCase().startsWith("critical")
                  ? "text-red-500"
                  : "text-amber-400"
              }
            />
          )}
        </div>
      )}

      {/* Sourcing quality (URL path) */}
      <SourcingBadge sq={data.sourcing_quality} />

      {/* Summary */}
      {data.summary && (
        <div className="p-4 bg-zinc-800/30 rounded-sm">
          <SectionHeader>AI Summary</SectionHeader>
          <p className="text-sm text-zinc-300 leading-relaxed">{data.summary}</p>
        </div>
      )}

      {/* Claims breakdown (URL path) */}
      <ClaimsBreakdown claims={data.claims} />

      {/* Strengths */}
      <TagList
        title="Journalism Strengths"
        items={data.strengths}
        icon={CheckCircle}
        iconColor="text-emerald-500"
        bg="bg-emerald-500/10"
        border="border-emerald-500/20"
      />

      {/* Legitimate elements (claim path) */}
      <TagList
        title="Legitimate Elements"
        items={data.legitimate_elements}
        icon={CheckCircle}
        iconColor="text-emerald-500"
        bg="bg-emerald-500/10"
        border="border-emerald-500/20"
      />

      {/* Concerns */}
      <TagList
        title="Concerns"
        items={data.concerns}
        icon={AlertTriangle}
        iconColor="text-amber-500"
        bg="bg-amber-500/10"
        border="border-amber-500/20"
      />

      {/* Red flags (claim path) */}
      <TagList
        title="Red Flags"
        items={data.red_flags}
        icon={AlertTriangle}
        iconColor="text-amber-500"
        bg="bg-amber-500/10"
        border="border-amber-500/20"
      />

      {/* Manipulation indicators */}
      <TagList
        title="Manipulation Indicators"
        items={manipIndicators}
        icon={Eye}
        iconColor="text-red-500"
        bg="bg-red-500/10"
        border="border-red-500/20"
      />

      {/* Emotional language / triggers */}
      <TagList
        title="Emotional Language"
        items={emotionalItems}
        icon={Hash}
        iconColor="text-orange-400"
        bg="bg-orange-500/10"
        border="border-orange-500/20"
      />

      {/* Missing context */}
      <TagList
        title="Missing Context"
        items={data.missing_context}
        icon={AlertCircle}
        iconColor="text-blue-400"
        bg="bg-blue-500/10"
        border="border-blue-500/20"
      />

      {/* Fact check priorities (URL path) */}
      <TagList
        title="Fact-Check Priorities"
        items={data.fact_check_priorities}
        icon={Search}
        iconColor="text-violet-400"
        bg="bg-violet-500/10"
        border="border-violet-500/20"
      />

      {/* Fact check suggestion (claim path) */}
      {data.fact_check_suggestion &&
        !data.fact_check_priorities?.length && (
          <div className="p-4 bg-zinc-800/30 rounded-sm">
            <h4 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
              <Search className="w-4 h-4 text-violet-400" />
              Fact-Check Suggestion
            </h4>
            <p className="text-sm text-zinc-400">{data.fact_check_suggestion}</p>
          </div>
        )}

      {/* Safety check verdict (compact) */}
      {data.safety_check && !data.safety_check.safe && (
        <div className="p-3 bg-red-900/20 border border-red-500/30 rounded-sm">
          <p className="text-xs text-red-400 font-semibold uppercase mb-1 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" /> Llama Guard flagged content
          </p>
          <p className="text-xs text-zinc-400">
            Categories: {data.safety_check.violated_category_labels?.join(", ") || "unspecified"}
          </p>
        </div>
      )}
    </motion.div>
  );
};

// ─── Document result panel ────────────────────────────────────────────────────
const DocumentResult = ({ data }) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    className="space-y-4"
  >
    {data.guardrails_blocked && <GuardrailsBlock violation={data.guard_violation} />}

    <div className="grid grid-cols-3 gap-3">
      <div className={`p-3 rounded-sm border ${riskBg(data.risk_score)}`}>
        <p className="text-xs text-zinc-500 mb-1 uppercase">Risk Score</p>
        <p className={`text-3xl font-bold font-mono ${riskColor(data.risk_score)}`}>
          {fmtScore(data.risk_score)}
        </p>
      </div>
      <div className="p-3 bg-zinc-800/50 rounded-sm">
        <p className="text-xs text-zinc-500 mb-1 uppercase">Fabrication</p>
        <div className="flex items-center gap-2 mt-1">
          {data.fabrication_detected ? (
            <XCircle className="w-5 h-5 text-red-500" />
          ) : (
            <CheckCircle className="w-5 h-5 text-emerald-500" />
          )}
          <span className={data.fabrication_detected ? "text-red-500 font-bold" : "text-emerald-500 font-bold"}>
            {data.fabrication_detected ? "Found" : "None"}
          </span>
        </div>
      </div>
      <div className="p-3 bg-zinc-800/50 rounded-sm">
        <p className="text-xs text-zinc-500 mb-1 uppercase">Overconfidence</p>
        <p className={`text-3xl font-bold font-mono ${riskColor(data.overconfidence_score)}`}>
          {fmtScore(data.overconfidence_score)}
        </p>
      </div>
    </div>

    {(data.tone_analysis || data.fabrication_details) && (
      <div className="grid grid-cols-2 gap-3">
        {data.tone_analysis && (
          <Chip label="Tone" value={pretty(data.tone_analysis)} color="text-zinc-300" />
        )}
        {data.fabrication_details && data.fabrication_details !== "null" && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-sm">
            <p className="text-xs text-zinc-500 mb-1 uppercase">Fabrication Detail</p>
            <p className="text-xs text-red-300">{data.fabrication_details}</p>
          </div>
        )}
      </div>
    )}

    {data.ai_summary && (
      <div className="p-4 bg-zinc-800/30 rounded-sm">
        <SectionHeader>AI Summary</SectionHeader>
        <p className="text-sm text-zinc-300 leading-relaxed">{data.ai_summary}</p>
      </div>
    )}

    <TagList
      title="Legal Issues"
      items={data.legal_issues}
      icon={AlertTriangle}
      iconColor="text-amber-500"
      bg="bg-amber-500/10"
      border="border-amber-500/20"
    />

    <TagList
      title="Harmful Claims"
      items={data.harmful_claims}
      icon={XCircle}
      iconColor="text-red-500"
      bg="bg-red-500/10"
      border="border-red-500/20"
    />

    <TagList
      title="Overconfident Phrases"
      items={data.overconfident_phrases}
      icon={AlertCircle}
      iconColor="text-orange-400"
      bg="bg-orange-500/10"
      border="border-orange-500/20"
    />

    <TagList
      title="Missing Disclosures"
      items={data.missing_disclosures}
      icon={Eye}
      iconColor="text-blue-400"
      bg="bg-blue-500/10"
      border="border-blue-500/20"
    />

    <TagList
      title="Credibility Markers"
      items={data.credibility_markers}
      icon={CheckCircle}
      iconColor="text-emerald-500"
      bg="bg-emerald-500/10"
      border="border-emerald-500/20"
    />

    <TagList
      title="Recommendations"
      items={data.recommendations}
      icon={Sparkles}
      iconColor="text-violet-400"
      bg="bg-violet-500/10"
      border="border-violet-500/20"
    />
  </motion.div>
);

// ════════════════════════════════════════════════════════════════════════════
// PAGE
// ════════════════════════════════════════════════════════════════════════════

export default function AnalyzePage() {
  const [documentForm, setDocumentForm] = useState({
    title: "",
    content: "",
    doc_type: "press_release",
    source: "",
  });
  const [claimContent, setClaimContent] = useState("");
  const [urlInput, setUrlInput] = useState("");
  const [urlContent, setUrlContent] = useState("");
  const [urlType, setUrlType] = useState("news_article");

  const [docAnalysis, setDocAnalysis] = useState(null);
  const [claimAnalysis, setClaimAnalysis] = useState(null);
  const [urlAnalysis, setUrlAnalysis] = useState(null);

  const [loadingDoc, setLoadingDoc] = useState(false);
  const [loadingClaim, setLoadingClaim] = useState(false);
  const [loadingUrl, setLoadingUrl] = useState(false);
  const [fetchError, setFetchError] = useState(null);

  // ── handlers ──────────────────────────────────────────────────────────────

  const analyzeDocument = async () => {
    if (!documentForm.title || !documentForm.content || !documentForm.source) {
      toast.error("Please fill in title, source and content");
      return;
    }
    setLoadingDoc(true);
    setDocAnalysis(null);
    try {
      const { data } = await axios.post(`${API}/layer1/analyze`, documentForm);
      setDocAnalysis(data);
      toast.success("Document analysis complete");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Analysis failed");
    } finally {
      setLoadingDoc(false);
    }
  };

  const analyzeClaim = async () => {
    if (!claimContent.trim()) {
      toast.error("Please enter a claim to analyse");
      return;
    }
    setLoadingClaim(true);
    setClaimAnalysis(null);
    try {
      const { data } = await axios.post(
        `${API}/layer2/analyze-claim?content=${encodeURIComponent(claimContent)}`
      );
      setClaimAnalysis(data);
      toast.success(
        data.input_type === "url_extracted_from_claim"
          ? "URL detected — article fetched and analysed"
          : "Claim analysis complete"
      );
    } catch (err) {
      toast.error(err.response?.data?.detail || "Analysis failed");
    } finally {
      setLoadingClaim(false);
    }
  };

  const analyzeUrl = async () => {
    if (!urlInput.trim()) {
      toast.error("Please enter a URL");
      return;
    }
    try {
      new URL(urlInput);
    } catch {
      toast.error("Please enter a valid URL (include https://)");
      return;
    }
    setLoadingUrl(true);
    setUrlAnalysis(null);
    setFetchError(null);
    try {
      const { data } = await axios.post(`${API}/layer2/analyze-url`, {
        url: urlInput,
        analysis_type: urlType,
        content: urlContent || null,
      });
      setUrlAnalysis(data);
      setFetchError(null);
      toast.success("URL analysis complete");
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg =
        typeof detail === "object" ? detail.message : detail || "Analysis failed";
      if (msg.toLowerCase().includes("fetch") || msg.toLowerCase().includes("paste")) {
        setFetchError(msg);
        toast.error("Auto-fetch failed — paste the article content below");
      } else {
        toast.error(msg);
      }
    } finally {
      setLoadingUrl(false);
    }
  };

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 md:p-8" data-testid="analyze-page">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white uppercase tracking-wide font-['Barlow_Condensed']">
          Deep Analysis
        </h1>
        <p className="text-zinc-500 text-sm mt-1">
          AI-powered misinformation detection via Llama 3.2 + Llama Guard 3
        </p>
      </div>

      <Tabs defaultValue="url" className="space-y-6">
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="url" className="data-[state=active]:bg-zinc-800" data-testid="tab-url">
            <Link className="w-4 h-4 mr-2" />
            Analyse URL
          </TabsTrigger>
          <TabsTrigger value="claim" className="data-[state=active]:bg-zinc-800" data-testid="tab-claim">
            <Globe className="w-4 h-4 mr-2" />
            Public Claim
          </TabsTrigger>
          <TabsTrigger value="document" className="data-[state=active]:bg-zinc-800" data-testid="tab-document">
            <FileText className="w-4 h-4 mr-2" />
            Official Document
          </TabsTrigger>
        </TabsList>

        {/* ── URL tab ── */}
        <TabsContent value="url" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card-tactical p-6" data-testid="url-form">
              <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
                URL Analysis
              </h2>
              <p className="text-xs text-zinc-500 mb-4">
                Paste a news article URL. If auto-fetch fails, paste the article text below.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">URL</label>
                  <Input
                    value={urlInput}
                    onChange={(e) => { setUrlInput(e.target.value); setFetchError(null); }}
                    placeholder="https://example.com/article..."
                    className="input-tactical"
                    data-testid="input-url"
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">Content Type</label>
                  <Select value={urlType} onValueChange={setUrlType}>
                    <SelectTrigger className="input-tactical" data-testid="select-url-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800">
                      <SelectItem value="news_article">News Article</SelectItem>
                      <SelectItem value="blog">Blog Post</SelectItem>
                      <SelectItem value="social_post">Social Media Post</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">
                    Article Content{" "}
                    {fetchError ? (
                      <span className="text-amber-400">(Required — auto-fetch failed)</span>
                    ) : (
                      <span className="text-zinc-600">(Optional paste-override)</span>
                    )}
                  </label>
                  <Textarea
                    value={urlContent}
                    onChange={(e) => setUrlContent(e.target.value)}
                    placeholder="Paste the article text here if automatic fetching fails…"
                    className={`input-tactical min-h-[100px] ${fetchError ? "border-amber-500/50" : ""}`}
                    data-testid="input-url-content"
                  />
                  {fetchError && (
                    <p className="text-xs text-amber-400 mt-1">{fetchError}</p>
                  )}
                </div>
                <Button
                  onClick={analyzeUrl}
                  disabled={loadingUrl}
                  className="w-full btn-primary"
                  data-testid="btn-analyze-url"
                >
                  {loadingUrl ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{urlContent ? "Analysing…" : "Fetching & Analysing…"}</>
                  ) : (
                    <><Sparkles className="w-4 h-4 mr-2" />{urlContent ? "Analyse Pasted Content" : "Analyse URL"}</>
                  )}
                </Button>
              </div>
            </div>

            <div className="card-tactical p-6 overflow-y-auto max-h-[80vh]" data-testid="url-results">
              <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
                Analysis Results
              </h2>
              {!urlAnalysis && !loadingUrl && <EmptyState icon={Link} text="Paste a URL to analyse" />}
              {loadingUrl && <LoadingState text={urlContent ? "Analysing content…" : "Fetching article…"} />}
              {urlAnalysis && <UrlAnalysisResult data={urlAnalysis} />}
            </div>
          </div>
        </TabsContent>

        {/* ── Claim tab ── */}
        <TabsContent value="claim" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card-tactical p-6" data-testid="claim-form">
              <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
                Claim Input
              </h2>
              <p className="text-xs text-zinc-500 mb-4">
                Paste a social-media post, forwarded message, or news headline. If your text
                contains a URL, the article will be fetched and analysed automatically.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">Claim / Text</label>
                  <Textarea
                    value={claimContent}
                    onChange={(e) => setClaimContent(e.target.value)}
                    placeholder="Paste a claim, forwarded message, or any text here…"
                    className="input-tactical min-h-[200px]"
                    data-testid="input-claim-content"
                  />
                </div>
                <Button
                  onClick={analyzeClaim}
                  disabled={loadingClaim}
                  className="w-full btn-primary"
                  data-testid="btn-analyze-claim"
                >
                  {loadingClaim ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Analysing…</>
                  ) : (
                    <><Sparkles className="w-4 h-4 mr-2" />Analyse Claim</>
                  )}
                </Button>
              </div>
            </div>

            <div className="card-tactical p-6 overflow-y-auto max-h-[80vh]" data-testid="claim-results">
              <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
                Analysis Results
              </h2>
              {!claimAnalysis && !loadingClaim && (
                <EmptyState icon={Globe} text="Submit a claim to see results" />
              )}
              {loadingClaim && <LoadingState text="Analysing claim…" />}
              {claimAnalysis && <UrlAnalysisResult data={claimAnalysis} />}
            </div>
          </div>
        </TabsContent>

        {/* ── Document tab ── */}
        <TabsContent value="document" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card-tactical p-6" data-testid="document-form">
              <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
                Document Input
              </h2>
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">Document Title</label>
                  <Input
                    value={documentForm.title}
                    onChange={(e) => setDocumentForm({ ...documentForm, title: e.target.value })}
                    placeholder="Enter document title…"
                    className="input-tactical"
                    data-testid="input-doc-title"
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">Source Organisation</label>
                  <Input
                    value={documentForm.source}
                    onChange={(e) => setDocumentForm({ ...documentForm, source: e.target.value })}
                    placeholder="e.g. Ministry of Finance"
                    className="input-tactical"
                    data-testid="input-doc-source"
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">Document Type</label>
                  <Select
                    value={documentForm.doc_type}
                    onValueChange={(v) => setDocumentForm({ ...documentForm, doc_type: v })}
                  >
                    <SelectTrigger className="input-tactical" data-testid="select-doc-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800">
                      <SelectItem value="press_release">Press Release</SelectItem>
                      <SelectItem value="regulatory_circular">Regulatory Circular</SelectItem>
                      <SelectItem value="public_advisory">Public Advisory</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase mb-1 block">Document Content</label>
                  <Textarea
                    value={documentForm.content}
                    onChange={(e) => setDocumentForm({ ...documentForm, content: e.target.value })}
                    placeholder="Paste the full document content here…"
                    className="input-tactical min-h-[200px]"
                    data-testid="input-doc-content"
                  />
                </div>
                <Button
                  onClick={analyzeDocument}
                  disabled={loadingDoc}
                  className="w-full btn-primary"
                  data-testid="btn-analyze-document"
                >
                  {loadingDoc ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Analysing…</>
                  ) : (
                    <><Sparkles className="w-4 h-4 mr-2" />Analyse Document</>
                  )}
                </Button>
              </div>
            </div>

            <div className="card-tactical p-6 overflow-y-auto max-h-[80vh]" data-testid="document-results">
              <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
                Analysis Results
              </h2>
              {!docAnalysis && !loadingDoc && (
                <EmptyState icon={Search} text="Submit a document to see results" />
              )}
              {loadingDoc && <LoadingState text="Analysing document…" />}
              {docAnalysis && <DocumentResult data={docAnalysis} />}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}