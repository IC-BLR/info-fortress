import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  Globe, 
  TrendingUp, 
  Users, 
  MessageSquare,
  AlertTriangle,
  RefreshCw,
  Filter
} from "lucide-react";
import { toast } from "sonner";
import { API } from "@/App";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import ClaimCard from "@/components/ClaimCard";
import VelocityChart from "@/components/VelocityChart";

export default function Layer2Page() {
  const [claims, setClaims] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [velocity, setVelocity] = useState([]);
  const [stats, setStats] = useState(null);
  const [trending, setTrending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  const fetchData = async () => {
    try {
      const [claimsRes, clustersRes, velocityRes, statsRes, trendingRes] = await Promise.all([
        axios.get(`${API}/layer2/claims`),
        axios.get(`${API}/layer2/clusters`),
        axios.get(`${API}/layer2/velocity`),
        axios.get(`${API}/layer2/stats`),
        axios.get(`${API}/layer2/trending`)
      ]);
      setClaims(claimsRes.data);
      setClusters(clustersRes.data);
      setVelocity(velocityRes.data);
      setStats(statsRes.data);
      setTrending(trendingRes.data);
    } catch (error) {
      console.error("Failed to fetch Layer 2 data:", error);
      toast.error("Failed to load narrative data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const filteredClaims = claims.filter(claim => {
    if (filter === "all") return true;
    if (filter === "high") return claim.risk_score >= 70;
    if (filter === "medium") return claim.risk_score >= 40 && claim.risk_score < 70;
    if (filter === "low") return claim.risk_score < 40;
    return claim.source_platform.toLowerCase().includes(filter.toLowerCase());
  });

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Globe className="w-12 h-12 text-zinc-600 mx-auto mb-4 animate-pulse" />
          <p className="text-zinc-500">Loading public narratives...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8" data-testid="layer2-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white uppercase tracking-wide font-['Barlow_Condensed']">
            Layer 2: Public Narrative Monitoring
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Social media, blogs, and alternative news tracking
          </p>
        </div>
        <button
          onClick={fetchData}
          className="btn-secondary flex items-center gap-2"
          data-testid="refresh-layer2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card-tactical p-4" data-testid="stat-claims-monitored">
            <p className="text-xs text-zinc-500 uppercase mb-1">Claims Monitored</p>
            <p className="text-2xl font-bold text-white font-mono">{stats.total_claims_monitored.toLocaleString()}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-high-risk-claims">
            <p className="text-xs text-zinc-500 uppercase mb-1">High Risk</p>
            <p className="text-2xl font-bold text-red-500 font-mono">{stats.high_risk_claims}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-avg-velocity">
            <p className="text-xs text-zinc-500 uppercase mb-1">Avg Velocity</p>
            <p className="text-2xl font-bold text-amber-500 font-mono">{stats.avg_velocity.toFixed(0)}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-total-amplification">
            <p className="text-xs text-zinc-500 uppercase mb-1">Total Amplification</p>
            <p className="text-2xl font-bold text-violet-500 font-mono">{(stats.total_amplification / 1000).toFixed(0)}k</p>
          </div>
        </div>
      )}

      {/* Velocity Chart */}
      <div className="card-tactical p-6 mb-6" data-testid="velocity-section">
        <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4 font-['Barlow_Condensed']">
          Narrative Velocity Tracking
        </h2>
        <VelocityChart data={velocity} />
      </div>

      {/* Main Content Tabs */}
      <Tabs defaultValue="claims" className="space-y-6">
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="claims" className="data-[state=active]:bg-zinc-800" data-testid="tab-claims">
            Claims Feed
          </TabsTrigger>
          <TabsTrigger value="clusters" className="data-[state=active]:bg-zinc-800" data-testid="tab-clusters">
            Claim Clusters
          </TabsTrigger>
          <TabsTrigger value="trending" className="data-[state=active]:bg-zinc-800" data-testid="tab-trending">
            Trending
          </TabsTrigger>
        </TabsList>

        {/* Claims Tab */}
        <TabsContent value="claims">
          <div className="space-y-4">
            {/* Filter Bar */}
            <div className="flex items-center gap-2 flex-wrap">
              <Filter className="w-4 h-4 text-zinc-500" />
              {["all", "high", "medium", "low"].map(f => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-3 py-1.5 rounded-sm text-xs font-medium transition-all ${
                    filter === f 
                      ? 'bg-white text-zinc-950' 
                      : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
                  }`}
                  data-testid={`filter-${f}`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>

            {/* Claims Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredClaims.map((claim, i) => (
                <ClaimCard key={claim.id} claim={claim} index={i} />
              ))}
            </div>
          </div>
        </TabsContent>

        {/* Clusters Tab */}
        <TabsContent value="clusters">
          <div className="space-y-4">
            {clusters.map((cluster, i) => (
              <motion.div
                key={cluster.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                className="card-tactical p-5"
                data-testid={`cluster-${cluster.id}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{cluster.theme}</h3>
                    <p className="text-xs text-zinc-500">
                      First seen: {new Date(cluster.first_seen).toLocaleDateString()}
                    </p>
                  </div>
                  <span className={`px-3 py-1 rounded-sm text-sm font-mono ${
                    cluster.avg_risk_score >= 70 ? 'bg-red-500/10 text-red-500 border border-red-500/20' :
                    cluster.avg_risk_score >= 40 ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20' :
                    'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                  }`}>
                    Risk: {cluster.avg_risk_score.toFixed(1)}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div>
                    <p className="text-xs text-zinc-500 mb-1">Claims</p>
                    <p className="text-xl font-bold text-white font-mono">{cluster.claim_count}</p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-500 mb-1">Velocity</p>
                    <p className="text-xl font-bold text-amber-500 font-mono">{cluster.velocity.toFixed(0)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-500 mb-1">Amplifiers</p>
                    <p className="text-xl font-bold text-violet-500 font-mono">{cluster.amplifiers.length}</p>
                  </div>
                </div>

                <div className="space-y-2">
                  <p className="text-xs text-zinc-500 uppercase">Top Claims</p>
                  <div className="flex flex-wrap gap-2">
                    {cluster.top_claims.map((claim, j) => (
                      <span key={j} className="text-xs px-2 py-1 bg-zinc-800 text-zinc-300 rounded-sm">
                        {claim}
                      </span>
                    ))}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </TabsContent>

        {/* Trending Tab */}
        <TabsContent value="trending">
          <div className="space-y-4">
            <p className="text-sm text-zinc-400 mb-4">
              Top trending narratives ranked by velocity
            </p>
            {trending.map((cluster, i) => (
              <motion.div
                key={cluster.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                className="card-tactical card-tactical-hover p-4 flex items-center gap-4"
                data-testid={`trending-${i}`}
              >
                <div className="flex-shrink-0 w-12 h-12 bg-zinc-800 rounded-sm flex items-center justify-center">
                  <span className="text-2xl font-bold text-zinc-400">#{i + 1}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="text-white font-semibold truncate">{cluster.theme}</h4>
                  <p className="text-xs text-zinc-500">{cluster.claim_count} claims</p>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-center">
                    <TrendingUp className="w-4 h-4 text-amber-500 mx-auto mb-1" />
                    <p className="text-sm font-mono text-amber-500">{cluster.velocity.toFixed(0)}</p>
                    <p className="text-[10px] text-zinc-500">velocity</p>
                  </div>
                  <div className="text-center">
                    <AlertTriangle className={`w-4 h-4 mx-auto mb-1 ${
                      cluster.avg_risk_score >= 70 ? 'text-red-500' : 
                      cluster.avg_risk_score >= 40 ? 'text-amber-500' : 'text-emerald-500'
                    }`} />
                    <p className={`text-sm font-mono ${
                      cluster.avg_risk_score >= 70 ? 'text-red-500' : 
                      cluster.avg_risk_score >= 40 ? 'text-amber-500' : 'text-emerald-500'
                    }`}>{cluster.avg_risk_score.toFixed(1)}</p>
                    <p className="text-[10px] text-zinc-500">risk</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
