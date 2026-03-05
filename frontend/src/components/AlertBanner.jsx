import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";

export default function AlertBanner({ alerts }) {
  const [dismissed, setDismissed] = useState([]);
  
  const visibleAlerts = alerts.filter((_, i) => !dismissed.includes(i));
  
  if (visibleAlerts.length === 0) return null;
  
  return (
    <div className="space-y-2 mb-6">
      <AnimatePresence>
        {alerts.map((alert, i) => {
          if (dismissed.includes(i)) return null;
          
          const isHigh = alert.includes("HIGH") || alert.includes("SYSTEM");
          
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: 100 }}
              className={`flex items-center justify-between p-3 rounded-sm border ${
                isHigh 
                  ? 'bg-red-500/10 border-red-500/20 text-red-500' 
                  : 'bg-amber-500/10 border-amber-500/20 text-amber-500'
              }`}
              data-testid={`alert-banner-${i}`}
            >
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm font-medium">{alert}</span>
              </div>
              <button
                onClick={() => setDismissed([...dismissed, i])}
                className="p-1 hover:bg-white/10 rounded-sm transition-colors"
                data-testid={`dismiss-alert-${i}`}
              >
                <X className="w-4 h-4" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
