import { motion } from "framer-motion";

export default function StatCard({ title, value, subtitle, icon: Icon, trend, color = "white" }) {
  const colorClasses = {
    white: "text-white",
    red: "text-red-500",
    amber: "text-amber-500",
    green: "text-emerald-500",
    violet: "text-violet-500",
    blue: "text-blue-500"
  };
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card-tactical p-4"
      data-testid={`stat-card-${title.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs text-zinc-500 uppercase tracking-wider">
          {title}
        </span>
        {Icon && <Icon className="w-4 h-4 text-zinc-600" strokeWidth={1.5} />}
      </div>
      
      <div className="flex items-baseline gap-2">
        <span className={`text-2xl font-bold font-mono ${colorClasses[color]}`}>
          {value}
        </span>
        {trend && (
          <span className={`text-xs font-medium ${
            trend > 0 ? 'text-red-500' : trend < 0 ? 'text-emerald-500' : 'text-zinc-500'
          }`}>
            {trend > 0 ? '+' : ''}{trend}%
          </span>
        )}
      </div>
      
      {subtitle && (
        <p className="text-xs text-zinc-500 mt-1">{subtitle}</p>
      )}
    </motion.div>
  );
}
