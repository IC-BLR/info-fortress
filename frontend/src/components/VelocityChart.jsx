import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { format, parseISO } from "date-fns";

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-zinc-900 border border-zinc-700 rounded-sm p-3 shadow-lg">
        <p className="text-zinc-400 text-xs mb-1">
          {format(parseISO(label), "MMM d, HH:mm")}
        </p>
        <p className="text-white font-mono text-sm">
          Velocity: <span className="text-amber-500">{payload[0].value.toFixed(0)}</span>
        </p>
        <p className="text-white font-mono text-sm">
          Claims: <span className="text-violet-500">{payload[1]?.value || 0}</span>
        </p>
      </div>
    );
  }
  return null;
};

export default function VelocityChart({ data }) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="velocityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="claimsGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="timestamp"
            tickFormatter={(val) => format(parseISO(val), "HH:mm")}
            stroke="#52525b"
            tick={{ fill: "#71717a", fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: "#27272a" }}
          />
          <YAxis
            stroke="#52525b"
            tick={{ fill: "#71717a", fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: "#27272a" }}
            width={40}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="velocity"
            stroke="#f59e0b"
            strokeWidth={2}
            fill="url(#velocityGradient)"
          />
          <Area
            type="monotone"
            dataKey="claim_count"
            stroke="#8b5cf6"
            strokeWidth={1}
            fill="url(#claimsGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
