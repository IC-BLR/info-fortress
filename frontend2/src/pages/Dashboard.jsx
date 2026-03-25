import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  Shield, 
  FileText, 
  Globe, 
  Activity, 
  AlertTriangle,
  TrendingUp,
  Users,
  RefreshCw
} from "lucide-react";
import { toast } from "sonner";
import { API } from "@/App";

import NRIGauge from "@/components/NRIGauge";
import VelocityChart from "@/components/VelocityChart";
import ClaimCard from "@/components/ClaimCard";
import PatternCard from "@/components/PatternCard";
import AlertBanner from "@/components/AlertBanner";
import StatCard from "@/components/StatCard";

export default function Dashboard() {
  const [nri, setNri] = useState(null);
  const [summary, setSummary] = useState(null);
  const [velocity, setVelocity] = useState([]);
  const [claims, setClaims] = useState([]);
  const [patterns, setPatterns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchDashboardData = async () => {
  try {
    const [
      nriRes,
      summaryRes,
      velocityRes,
      claimsRes,
      patternsRes
    ] = await Promise.all([
      axios.get(`${API}/dashboard/nri`),
      axios.get(`${API}/dashboard/summary`),
      axios.get(`${API}/layer2/velocity`),
      axios.get(`${API}/layer2/claims`),
      axios.get(`${API}/layer3/patterns`)
    ]);

    setNri(nriRes.data);
    setSummary(summaryRes.data);

    // ✅ FIX: unwrap backend response shapes
    setVelocity(
      Array.isArray(velocityRes.data?.data)
        ? velocityRes.data.data.map(d => ({
            date: d.date,
            count: d.claim_count,
            risk: d.avg_risk
          }))
        : []
    );

    setClaims(Array.isArray(claimsRes.data?.items)
      ? claimsRes.data.items
      : []);

    setPatterns(Array.isArray(patternsRes.data?.patterns)
      ? patternsRes.data.patterns
      : []);

  } catch (error) {
    console.error("Failed to fetch dashboard data:", error);
    toast.error("Failed to load dashboard data");
  } finally {
    setLoading(false);
    setRefreshing(false);
  }
};

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchDashboardData();
    toast.success("Dashboard refreshed");
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Shield className="w-12 h-12 text-zinc-600 mx-auto mb-4 animate-pulse" />
          <p className="text-zinc-500">Loading INFO FORTRESS...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8" data-testid="dashboard-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white uppercase tracking-wide font-['Barlow_Condensed']">
            Narrative Risk Dashboard
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Real-time misinformation threat monitoring
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="btn-secondary flex items-center gap-2"
          data-testid="refresh-dashboard"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Alerts */}
      {nri?.alerts && <AlertBanner alerts={nri.alerts} />}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* NRI Gauge - Main metric */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="card-tactical p-6 lg:col-span-1"
          data-testid="nri-gauge-card"
        >
          <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
            Narrative Risk Index
          </h2>
          {nri && <NRIGauge score={nri.overall_score} trend={nri.trend} />}
          
          {/* Layer breakdown */}
          {nri && (
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-500 flex items-center gap-2">
                  <FileText className="w-3 h-3" /> Layer 1 - Official
                </span>
                <span className="text-sm font-mono text-blue-500">{nri?.layer1_score?.toFixed(1)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-500 flex items-center gap-2">
                  <Globe className="w-3 h-3" /> Layer 2 - Public
                </span>
                <span className="text-sm font-mono text-amber-500">{nri?.layer2_score?.toFixed(1)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-500 flex items-center gap-2">
                  <Shield className="w-3 h-3" /> Layer 3 - Systemic
                </span>
                <span className="text-sm font-mono text-violet-500">{nri?.layer3_score?.toFixed(1)}</span>
              </div>
            </div>
          )}
        </motion.div>

        {/* Velocity Chart */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="card-tactical p-6 lg:col-span-2"
          data-testid="velocity-chart-card"
        >
          <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
            Claim Velocity (24h)
          </h2>
          <VelocityChart data={velocity} />
        </motion.div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          title="Documents Analyzed"
          value={summary?.total_documents_analyzed || 0}
          icon={FileText}
          color="blue"
        />
        <StatCard
          title="Active Clusters"
          value={summary?.active_claim_clusters || 0}
          icon={Activity}
          color="amber"
        />
        <StatCard
          title="Patterns Detected"
          value={summary?.patterns_detected || 0}
          icon={Shield}
          color="violet"
        />
        <StatCard
          title="High Risk Claims"
          value={summary?.high_risk_claims || 0}
          icon={AlertTriangle}
          color="red"
        />
      </div>

      {/* Bottom Grid - Claims and Patterns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent High-Risk Claims */}
        <motion.div
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="card-tactical p-6"
          data-testid="claims-panel"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white uppercase tracking-wide font-['Barlow_Condensed']">
              High-Risk Claims
            </h2>
            <span className="text-xs text-zinc-500">Layer 2</span>
          </div>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {claims
              .filter(c => c.risk_score > 60)
              .slice(0, 4)
              .map((claim, i) => (
                <ClaimCard key={claim.id} claim={claim} index={i} />
              ))}
          </div>
        </motion.div>

        {/* Active Patterns */}
        <motion.div
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="card-tactical p-6"
          data-testid="patterns-panel"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white uppercase tracking-wide font-['Barlow_Condensed']">
              Active Systemic Patterns
            </h2>
            <span className="text-xs text-zinc-500">Layer 3</span>
          </div>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {patterns.slice(0, 4).map((pattern, i) => (
              <PatternCard key={pattern.id} pattern={pattern} index={i} />
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
