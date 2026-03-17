import { useState, useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";

// Components
import Sidebar from "@/components/Sidebar";
import Dashboard from "@/pages/Dashboard";
import Layer1Page from "@/pages/Layer1Page";
import Layer2Page from "@/pages/Layer2Page";
import Layer3Page from "@/pages/Layer3Page";
import AnalyzePage from "@/pages/AnalyzePage";

const BACKEND_URL = "https://assets.indiainnovationcentre.com/info-war/backend";
export const API = `${BACKEND_URL}/api`;

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    
      <BrowserRouter basename="/info-war/">
       

          <Routes>
            {/* <Route path="/" element={<Dashboard />} />
            <Route path="/layer1" element={<Layer1Page />} />
            <Route path="/layer2" element={<Layer2Page />} />
            <Route path="/layer3" element={<Layer3Page />} /> */}
            <Route path="/" element={<AnalyzePage />} />
          </Routes>
        
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    
  );
}

export default App;
