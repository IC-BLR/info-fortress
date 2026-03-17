import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import {
  Shield,
  RefreshCw,
  AlertOctagon
} from "lucide-react";
import { toast } from "sonner";
import { API } from "@/App";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip
} from "recharts";

import PatternCard from "@/components/PatternCard";

export default function Layer3Page() {
  const [patterns, setPatterns] = useState([]);
  const [threatMap, setThreatMap] = useState([]);
  const [stats, setStats] = useState(null);
  const [resilience, setResilience] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [patternsRes, threatMapRes, statsRes, resilienceRes] =
        await Promise.all([
          axios.get(`${API}/layer3/patterns`),
          axios.get(`${API}/layer3/threat-map`),
          axios.get(`${API}/layer3/stats`),
          axios.get(`${API}/layer3/resilience-score`)
        ]);

      setPatterns(
        Array.isArray(patternsRes.data?.patterns)
          ? patternsRes.data.patterns
          : []
      );

      setThreatMap(
        Array.isArray(threatMapRes.data?.nodes)
          ? threatMapRes.data.nodes
          : []
      );

      setStats(statsRes.data ?? null);
      setResilience(resilienceRes.data ?? null);

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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Shield className="w-12 h-12 text-zinc-600 mx-auto mb-4 animate-pulse" />
          <p className="text-zinc-500">
            Analyzing systemic patterns...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8">
      {/* Resilience Score */}
      {resilience && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="card-tactical p-6 mb-6"
        >
          <h2 className="text-lg font-semibold text-white mb-2">
            System Resilience Score
          </h2>

          <div className="flex items-baseline gap-4">
            <span className="text-5xl font-bold font-mono text-white">
              {Number(resilience.resilience_score ?? 0).toFixed(0)}
            </span>
            <span className="text-sm text-zinc-400 uppercase">
              {resilience.threat_level}
            </span>
          </div>

          <p className="text-sm text-zinc-400 mt-2">
            <AlertOctagon className="w-4 h-4 inline mr-1" />
            {resilience.active_threats ?? 0} active threats
          </p>
        </motion.div>
      )}

      {/* Basic Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-2 gap-4 mb-6">
          <div className="card-tactical p-4">
            <p className="text-xs text-zinc-500 uppercase mb-1">
              Total Documents
            </p>
            <p className="text-2xl font-bold text-white font-mono">
              {stats.total_documents ?? 0}
            </p>
          </div>

          <div className="card-tactical p-4">
            <p className="text-xs text-zinc-500 uppercase mb-1">
              Total Claims
            </p>
            <p className="text-2xl font-bold text-white font-mono">
              {stats.total_claims ?? 0}
            </p>
          </div>
        </div>
      )}

      {/* Threat Map Pie */}
      {threatMap.length > 0 && (
        <div className="card-tactical p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Threat Map
          </h2>
          <div style={{ width: "100%", height: 250 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={threatMap}
                  dataKey="claim_count"
                  nameKey="label"
                  outerRadius={90}
                >
                  {threatMap.map((entry, index) => (
                    <Cell
                      key={index}
                      fill={
                        entry.threat_level === "high"
                          ? "#ef4444"
                          : entry.threat_level === "medium"
                          ? "#f59e0b"
                          : "#22c55e"
                      }
                    />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Patterns */}
      <div className="card-tactical p-6">
        <h2 className="text-lg font-semibold text-white mb-4">
          Detected Systemic Patterns
        </h2>
        <div className="space-y-4">
          {patterns.map((pattern, i) => (
            <PatternCard key={pattern.id} pattern={pattern} index={i} />
          ))}
        </div>
      </div>
    </div>
  );
}