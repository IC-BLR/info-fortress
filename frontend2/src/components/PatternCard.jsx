import { motion } from "framer-motion";
import { GitBranch, Building2, Bot, Users2, Clock, FileWarning } from "lucide-react";

const patternIcons = {
  coordinated_distortion: { icon: GitBranch, color: "text-red-500", bg: "bg-red-500/10" },
  institutional_undermining: { icon: Building2, color: "text-amber-500", bg: "bg-amber-500/10" },
  synthetic_authority: { icon: Bot, color: "text-violet-500", bg: "bg-violet-500/10" },
  manufactured_consensus: { icon: Users2, color: "text-blue-500", bg: "bg-blue-500/10" },
};

function formatPatternType(type) {
  if (!type || typeof type !== "string") return "Unknown Pattern";
  return type.split("_")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export default function PatternCard({ pattern, index = 0 }) {
  const iconConfig = patternIcons[pattern.pattern_type] || { 
    icon: FileWarning, 
    color: "text-zinc-400", 
    bg: "bg-zinc-500/10" 
  };
  const IconComponent = iconConfig.icon;
  
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1 }}
      className="card-tactical card-tactical-hover p-4"
      data-testid={`pattern-card-${pattern.id}`}
    >
      <div className="flex items-start gap-4">
        <div className={`pattern-icon ${iconConfig.bg}`}>
          <IconComponent className={`w-5 h-5 ${iconConfig.color}`} strokeWidth={1.5} />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-white uppercase tracking-wide">
              {formatPatternType(pattern.pattern_type)}
            </h4>
            <span className="text-xs font-mono px-2 py-0.5 bg-zinc-800 rounded-sm text-zinc-300">
              {pattern.confidence.toFixed(1)}% conf
            </span>
          </div>
          
          <p className="text-xs text-zinc-400 mb-3 line-clamp-2">
            {pattern.description}
          </p>
          
          <div className="flex flex-wrap gap-1 mb-3">
            {pattern.affected_entities.slice(0, 3).map((entity, i) => (
              <span 
                key={i}
                className="text-[10px] px-2 py-0.5 bg-zinc-800/50 text-zinc-400 rounded-sm"
              >
                {entity}
              </span>
            ))}
            {pattern.affected_entities.length > 3 && (
              <span className="text-[10px] px-2 py-0.5 bg-zinc-800/50 text-zinc-500 rounded-sm">
                +{pattern.affected_entities.length - 3} more
              </span>
            )}
          </div>
          
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <span className="flex items-center gap-1">
              <FileWarning className="w-3 h-3" />
              {pattern.evidence_count} evidence items
            </span>
            <span className={`font-mono ${
              pattern.risk_contribution > 20 ? 'text-red-500' : 
              pattern.risk_contribution > 10 ? 'text-amber-500' : 'text-emerald-500'
            }`}>
              +{pattern.risk_contribution.toFixed(1)} NRI
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
