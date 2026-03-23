import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import {
  Globe,
  TrendingUp,
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
      const [
        claimsRes,
        clustersRes,
        velocityRes,
        statsRes,
        trendingRes
      ] = await Promise.all([
        axios.get(`${API}/layer2/claims`),
        axios.get(`${API}/layer2/clusters`),
        axios.get(`${API}/layer2/velocity`),
        axios.get(`${API}/layer2/stats`),
        axios.get(`${API}/layer2/trending`)
      ]);

      // Unwrap backend response shapes safely
      setClaims(Array.isArray(claimsRes.data?.items) ? claimsRes.data.items : []);
      setClusters(Array.isArray(clustersRes.data?.clusters) ? clustersRes.data.clusters : []);
      setVelocity(Array.isArray(velocityRes.data?.data) ? velocityRes.data.data : []);
      setTrending(Array.isArray(trendingRes.data?.trending) ? trendingRes.data.trending : []);
      setStats(statsRes.data ?? null);

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

  // Safe filtering
  const filteredClaims = Array.isArray(claims)
    ? claims.filter((claim) => {
        const risk = Number(claim?.risk_score ?? 0);

        if (filter === "all") return true;
        if (filter === "high") return risk >= 70;
        if (filter === "medium") return risk >= 40 && risk < 70;
        if (filter === "low") return risk < 40;

        return (claim?.source_domain || "")
          .toLowerCase()
          .includes(filter.toLowerCase());
      })
    : [];

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
    <div className="p-6 md:p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white uppercase tracking-wide">
            Layer 2: Public Narrative Monitoring
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Social media, blogs, and alternative news tracking
          </p>
        </div>
        <button
          onClick={fetchData}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card-tactical p-4">
            <p className="text-xs text-zinc-500 uppercase mb-1">
              Claims Monitored
            </p>
            <p className="text-2xl font-bold text-white font-mono">
              {(stats.total_claims_analyzed ?? 0).toLocaleString()}
            </p>
          </div>

          <div className="card-tactical p-4">
            <p className="text-xs text-zinc-500 uppercase mb-1">
              High Risk
            </p>
            <p className="text-2xl font-bold text-red-500 font-mono">
              {stats.high_risk_count ?? 0}
            </p>
          </div>

          <div className="card-tactical p-4">
            <p className="text-xs text-zinc-500 uppercase mb-1">
              Avg Risk
            </p>
            <p className="text-2xl font-bold text-amber-500 font-mono">
              {Number(stats.avg_risk_score ?? 0).toFixed(1)}
            </p>
          </div>

          <div className="card-tactical p-4">
            <p className="text-xs text-zinc-500 uppercase mb-1">
              Flagged
            </p>
            <p className="text-2xl font-bold text-violet-500 font-mono">
              {stats.flagged_count ?? 0}
            </p>
          </div>
        </div>
      )}

      {/* Velocity Chart */}
      <div className="card-tactical p-6 mb-6">
        <h2 className="text-lg font-semibold text-white uppercase tracking-wide mb-4">
          Narrative Velocity Tracking
        </h2>
        <VelocityChart data={velocity} />
      </div>

      {/* Tabs */}
      <Tabs defaultValue="claims" className="space-y-6">
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="claims">Claims Feed</TabsTrigger>
          <TabsTrigger value="clusters">Claim Clusters</TabsTrigger>
          <TabsTrigger value="trending">Trending</TabsTrigger>
        </TabsList>

        {/* Claims Tab */}
        <TabsContent value="claims">
          <div className="space-y-4">
            <div className="flex items-center gap-2 flex-wrap">
              <Filter className="w-4 h-4 text-zinc-500" />
              {["all", "high", "medium", "low"].map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-3 py-1.5 rounded-sm text-xs ${
                    filter === f
                      ? "bg-white text-zinc-950"
                      : "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>

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
              >
                <h3 className="text-lg font-semibold text-white">
                  {cluster.source_domain}
                </h3>
                <p className="text-sm text-zinc-400">
                  Claims: {cluster.claim_count ?? 0}
                </p>
                <p className="text-sm text-amber-500">
                  Avg Risk: {Number(cluster.avg_risk ?? 0).toFixed(1)}
                </p>
              </motion.div>
            ))}
          </div>
        </TabsContent>

        {/* Trending Tab */}
        <TabsContent value="trending">
          <div className="space-y-4">
            {trending.map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                className="card-tactical p-4"
              >
                <h4 className="text-white font-semibold">
                  {item.source_domain}
                </h4>
                <p className="text-sm text-zinc-400">
                  {item.claim_count ?? 0} claims
                </p>
                <p className="text-sm text-amber-500">
                  Avg Risk: {Number(item.avg_risk ?? 0).toFixed(1)}
                </p>
              </motion.div>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}