import { motion } from "framer-motion";
import { TrendingUp, Users, MessageSquare, AlertTriangle } from "lucide-react";

const getRiskBadge = (score) => {
  if (score >= 70) return { label: "HIGH RISK", class: "badge-risk-high" };
  if (score >= 40) return { label: "MEDIUM", class: "badge-risk-medium" };
  return { label: "LOW", class: "badge-risk-low" };
};

const getSentimentIcon = (sentiment) => {
  if (sentiment === "alarming") return <AlertTriangle className="w-4 h-4 text-red-500" />;
  if (sentiment === "negative") return <AlertTriangle className="w-4 h-4 text-amber-500" />;
  return null;
};

export default function ClaimCard({ claim, index = 0 }) {
  const risk = getRiskBadge(claim.risk_score);
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="card-tactical card-tactical-hover p-4 claim-card"
      data-testid={`claim-card-${claim.id}`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={risk.class}>{risk.label}</span>
          {getSentimentIcon(claim.sentiment)}
        </div>
        <span className="text-xs text-zinc-500 font-mono">
          {claim.source_platform}
        </span>
      </div>
      
      <p className="text-sm text-zinc-200 mb-3 line-clamp-2">
        {claim.content}
      </p>
      
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span className="flex items-center gap-1">
          <MessageSquare className="w-3 h-3" />
          {claim.source_user}
        </span>
        
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1" title="Velocity">
            <TrendingUp className="w-3 h-3 text-amber-500" />
            <span className="font-mono">{claim.velocity?.toFixed(0)}</span>
          </span>
          <span className="flex items-center gap-1" title="Amplification">
            <Users className="w-3 h-3 text-violet-500" />
            <span className="font-mono">{(claim.amplification_count / 1000).toFixed(1)}k</span>
          </span>
        </div>
      </div>
      
      {/* Risk meter */}
      <div className="mt-3 risk-meter">
        <div 
          className="risk-meter-fill"
          style={{ 
            width: `${claim.risk_score}%`,
            backgroundColor: claim.risk_score >= 70 ? '#ef4444' : claim.risk_score >= 40 ? '#f59e0b' : '#22c55e'
          }}
        />
      </div>
    </motion.div>
  );
}
