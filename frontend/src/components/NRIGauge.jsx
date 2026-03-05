import { RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis } from "recharts";
import { motion } from "framer-motion";

export default function NRIGauge({ score, trend }) {
  const getColor = (score) => {
    if (score >= 70) return "#ef4444"; // red
    if (score >= 40) return "#f59e0b"; // amber
    return "#22c55e"; // green
  };

  const color = getColor(score);
  
  const data = [
    { name: "NRI", value: score, fill: color }
  ];

  const getTrendIcon = () => {
    if (trend === "rising") return "↑";
    if (trend === "falling") return "↓";
    return "→";
  };

  const getTrendColor = () => {
    if (trend === "rising") return "text-red-500";
    if (trend === "falling") return "text-emerald-500";
    return "text-amber-500";
  };

  return (
    <div className="relative w-full h-64 flex items-center justify-center">
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="60%"
          outerRadius="90%"
          barSize={20}
          data={data}
          startAngle={180}
          endAngle={0}
        >
          <PolarAngleAxis
            type="number"
            domain={[0, 100]}
            angleAxisId={0}
            tick={false}
          />
          <RadialBar
            background={{ fill: "hsl(240 4% 14%)" }}
            dataKey="value"
            cornerRadius={4}
            angleAxisId={0}
          />
        </RadialBarChart>
      </ResponsiveContainer>
      
      {/* Center value display */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <motion.span
          key={score}
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="text-5xl font-bold font-mono"
          style={{ color }}
        >
          {score.toFixed(0)}
        </motion.span>
        <span className="text-zinc-500 text-sm uppercase tracking-wider mt-1">
          Risk Index
        </span>
        <span className={`text-lg font-semibold ${getTrendColor()} mt-1`}>
          {getTrendIcon()} {trend}
        </span>
      </div>

      {/* Scale markers */}
      <div className="absolute bottom-8 left-0 right-0 flex justify-between px-8 text-xs text-zinc-500 font-mono">
        <span>0</span>
        <span>50</span>
        <span>100</span>
      </div>
    </div>
  );
}
