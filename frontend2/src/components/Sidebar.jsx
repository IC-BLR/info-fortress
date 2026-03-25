import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import { 
  LayoutDashboard, 
  FileText, 
  Globe, 
  Shield, 
  Search,
  ChevronLeft,
  ChevronRight,
  Activity
} from "lucide-react";

const navItems = [
  { path: "/", icon: LayoutDashboard, label: "Dashboard", description: "NRI Overview" },
  { path: "/layer1", icon: FileText, label: "Layer 1", description: "Official Comms" },
  { path: "/layer2", icon: Globe, label: "Layer 2", description: "Narrative Monitor" },
  { path: "/layer3", icon: Shield, label: "Layer 3", description: "Systemic Resilience" },
  { path: "/analyze", icon: Search, label: "Analyze", description: "Deep Analysis" },
];

export default function Sidebar({ collapsed, onToggle }) {
  return (
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''} flex flex-col`}>
      {/* Logo Section */}
      <div className="p-4 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-sm bg-white flex items-center justify-center flex-shrink-0">
            <Shield className="w-6 h-6 text-zinc-950" strokeWidth={1.5} />
          </div>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="overflow-hidden"
            >
              <h1 className="text-lg font-bold text-white uppercase tracking-wider font-['Barlow_Condensed']">
                INFO FORTRESS
              </h1>
              <p className="text-[10px] text-zinc-500 uppercase tracking-widest">
                Misinformation Defense
              </p>
            </motion.div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            data-testid={`nav-${item.label.toLowerCase().replace(' ', '-')}`}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-sm transition-all duration-200 group
              ${isActive 
                ? 'bg-zinc-800 text-white' 
                : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
              }`
            }
          >
            <item.icon className="w-5 h-5 flex-shrink-0" strokeWidth={1.5} />
            {!collapsed && (
              <div className="overflow-hidden">
                <p className="text-sm font-medium">{item.label}</p>
                <p className="text-[10px] text-zinc-500 group-hover:text-zinc-400">
                  {item.description}
                </p>
              </div>
            )}
          </NavLink>
        ))}
      </nav>

      {/* System Status */}
      {!collapsed && (
        <div className="p-4 border-t border-zinc-800">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Activity className="w-3 h-3 text-emerald-500" />
            <span>System Active</span>
          </div>
          <p className="text-[10px] text-zinc-600 mt-1 font-mono">
            Last sync: {new Date().toLocaleTimeString()}
          </p>
        </div>
      )}

      {/* Collapse Toggle */}
      <button
        onClick={onToggle}
        data-testid="sidebar-toggle"
        className="absolute -right-3 top-20 w-6 h-6 bg-zinc-800 border border-zinc-700 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all"
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4" />
        ) : (
          <ChevronLeft className="w-4 h-4" />
        )}
      </button>
    </aside>
  );
}
