import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { parseISO, isValid, format } from "date-fns";

function CustomTooltip({ active, payload }) {
  if (!active || !payload || payload.length === 0) return null;

  const dateValue = payload?.[0]?.payload?.date;
  if (!dateValue) return null;

  const parsed = parseISO(dateValue);
  if (!isValid(parsed)) return null;

  return (
    <div className="bg-zinc-900 border border-zinc-800 p-3 rounded text-xs">
      <p className="text-zinc-400 mb-1">
        {format(parsed, "MMM dd, yyyy")}
      </p>
      <p className="text-white">
        Claims: {payload[0]?.payload?.claim_count ?? 0}
      </p>
      <p className="text-amber-400">
        Avg Risk: {(payload[0]?.payload?.avg_risk ?? 0).toFixed(1)}
      </p>
    </div>
  );
}

export default function VelocityChart({ data }) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="claimsGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
            </linearGradient>
          </defs>

          {/* FIXED: use "date" not "timestamp" */}
          <XAxis
            dataKey="date"
            tickFormatter={(val) => {
              const parsed = parseISO(val);
              return isValid(parsed) ? format(parsed, "MM/dd") : "";
            }}
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

          {/* Claims count area */}
          <Area
            type="monotone"
            dataKey="claim_count"
            stroke="#8b5cf6"
            strokeWidth={2}
            fill="url(#claimsGradient)"
          />

          {/* Average risk area */}
          <Area
            type="monotone"
            dataKey="avg_risk"
            stroke="#f59e0b"
            strokeWidth={2}
            fill="url(#riskGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}