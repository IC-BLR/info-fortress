import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  Shield, 
  GitBranch, 
  Building2, 
  Bot, 
  Users2,
  RefreshCw,
  Activity,
  AlertOctagon
} from "lucide-react";
import { toast } from "sonner";
import { API } from "@/App";
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from "recharts";

import PatternCard from "@/components/PatternCard";

const patternTypeInfo = {
  coordinated_distortion: { icon: GitBranch, label: "Coordinated Distortion", color: "#ef4444" },
  institutional_undermining: { icon: Building2, label: "Institutional Undermining", color: "#f59e0b" },
  synthetic_authority: { icon: Bot, label: "Synthetic Authority", color: "#8b5cf6" },
  manufactured_consensus: { icon: Users2, label: "Manufactured Consensus", color: "#3b82f6" },
};

export default function Layer3Page() {
  const [patterns, setPatterns] = useState([]);
  const [threatMap, setThreatMap] = useState(null);
  const [stats, setStats] = useState(null);
  const [resilience, setResilience] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [patternsRes, threatMapRes, statsRes, resilienceRes] = await Promise.all([
        axios.get(`${API}/layer3/patterns`),
        axios.get(`${API}/layer3/threat-map`),
        axios.get(`${API}/layer3/stats`),
        axios.get(`${API}/layer3/resilience-score`)
      ]);
      setPatterns(patternsRes.data);
      setThreatMap(threatMapRes.data);
      setStats(statsRes.data);
      setResilience(resilienceRes.data);
    } catch (error) {
      console.error("Failed to fetch Layer 3 data:", error);
      toast.error("Failed to load systemic patterns");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const threatMapData = threatMap ? Object.entries(threatMap).map(([key, value]) => ({
    name: patternTypeInfo[key]?.label || key,
    count: value.count,
    risk: value.total_risk,
    color: patternTypeInfo[key]?.color || "#71717a"
  })) : [];

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Shield className="w-12 h-12 text-zinc-600 mx-auto mb-4 animate-pulse" />
          <p className="text-zinc-500">Analyzing systemic patterns...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8" data-testid="layer3-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white uppercase tracking-wide font-['Barlow_Condensed']">
            Layer 3: Systemic Resilience Engine
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Pattern emergence, coordination detection, and institutional threat analysis
          </p>
        </div>
        <button
          onClick={fetchData}
          className="btn-secondary flex items-center gap-2"
          data-testid="refresh-layer3"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Resilience Score Hero */}
      {resilience && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className={`card-tactical p-6 mb-6 border-l-4 ${
            resilience.threat_level === 'high' ? 'border-l-red-500' :
            resilience.threat_level === 'medium' ? 'border-l-amber-500' : 'border-l-emerald-500'
          }`}
          data-testid="resilience-hero"
        >
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white uppercase tracking-wide font-['Barlow_Condensed'] mb-2">
                System Resilience Score
              </h2>
              <div className="flex items-baseline gap-4">
                <span className={`text-5xl font-bold font-mono ${
                  resilience.resilience_score >= 70 ? 'text-emerald-500' :
                  resilience.resilience_score >= 40 ? 'text-amber-500' : 'text-red-500'
                }`}>
                  {resilience.resilience_score.toFixed(0)}
                </span>
                <span className={`text-sm uppercase tracking-wider px-3 py-1 rounded-sm ${
                  resilience.threat_level === 'high' ? 'bg-red-500/10 text-red-500' :
                  resilience.threat_level === 'medium' ? 'bg-amber-500/10 text-amber-500' : 
                  'bg-emerald-500/10 text-emerald-500'
                }`}>
                  {resilience.threat_level} threat
                </span>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm text-zinc-400 mb-2">
                <AlertOctagon className="w-4 h-4 inline mr-1" />
                {resilience.active_threats} active threats
              </p>
              <p className="text-xs text-zinc-500">{resilience.recommendation}</p>
            </div>
          </div>
          
          {/* Resilience bar */}
          <div className="mt-4 h-3 bg-zinc-800 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${resilience.resilience_score}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
              className={`h-full ${
                resilience.resilience_score >= 70 ? 'bg-emerald-500' :
                resilience.resilience_score >= 40 ? 'bg-amber-500' : 'bg-red-500'
              }`}
            />
          </div>
        </motion.div>
      )}

      {/* Stats Row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card-tactical p-4" data-testid="stat-patterns">
            <p className="text-xs text-zinc-500 uppercase mb-1">Patterns Detected</p>
            <p className="text-2xl font-bold text-white font-mono">{stats.total_patterns_detected}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-confidence">
            <p className="text-xs text-zinc-500 uppercase mb-1">Avg Confidence</p>
            <p className="text-2xl font-bold text-violet-500 font-mono">{stats.avg_confidence.toFixed(1)}%</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-evidence">
            <p className="text-xs text-zinc-500 uppercase mb-1">Evidence Items</p>
            <p className="text-2xl font-bold text-blue-500 font-mono">{stats.total_evidence_items}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-risk-contrib">
            <p className="text-xs text-zinc-500 uppercase mb-1">Total Risk Impact</p>
            <p className="text-2xl font-bold text-red-500 font-mono">+{stats.total_risk_contribution.toFixed(1)}</p>
          </div>
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Threat Distribution Pie */}
        <div className="card-tactical p-6" data-testid="threat-distribution">
          <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
            Threat Type Distribution
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={threatMapData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="count"
                >
                  {threatMapData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-4">
            {threatMapData.map((item, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: item.color }} />
                <span className="text-zinc-400">{item.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Risk Contribution Bar */}
        <div className="card-tactical p-6" data-testid="risk-contribution-chart">
          <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
            Risk Contribution by Type
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={threatMapData} layout="vertical">
                <XAxis type="number" stroke="#52525b" tick={{ fill: "#71717a", fontSize: 10 }} />
                <YAxis type="category" dataKey="name" width={100} stroke="#52525b" tick={{ fill: "#71717a", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '4px' }}
                  labelStyle={{ color: '#f4f4f5' }}
                />
                <Bar dataKey="risk" fill="#8884d8">
                  {threatMapData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Detected Patterns */}
      <div className="card-tactical p-6" data-testid="patterns-section">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white uppercase tracking-wide font-['Barlow_Condensed']">
            Detected Systemic Patterns
          </h2>
          <span className="text-xs text-zinc-500">{patterns.length} patterns active</span>
        </div>
        <div className="space-y-4">
          {patterns.map((pattern, i) => (
            <PatternCard key={pattern.id} pattern={pattern} index={i} />
          ))}
        </div>
      </div>

      {/* Affected Entities */}
      {stats && stats.affected_entities.length > 0 && (
        <div className="card-tactical p-6 mt-6" data-testid="affected-entities">
          <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
            Targeted Institutions
          </h2>
          <div className="flex flex-wrap gap-2">
            {stats.affected_entities.map((entity, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.05 }}
                className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-sm text-sm text-zinc-300 flex items-center gap-2"
              >
                <Building2 className="w-3 h-3 text-amber-500" />
                {entity}
              </motion.span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
