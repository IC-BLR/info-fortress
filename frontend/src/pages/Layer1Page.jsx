import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  FileText, 
  AlertTriangle, 
  CheckCircle, 
  XCircle,
  Scale,
  TrendingUp,
  RefreshCw,
  Eye
} from "lucide-react";
import { toast } from "sonner";
import { API } from "@/App";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const getDocTypeIcon = (type) => {
  switch (type) {
    case "press_release": return "PR";
    case "regulatory_circular": return "RC";
    case "public_advisory": return "PA";
    default: return "DOC";
  }
};

const getRiskColor = (score) => {
  if (score >= 40) return "text-red-500";
  if (score >= 20) return "text-amber-500";
  return "text-emerald-500";
};

export default function Layer1Page() {
  const [documents, setDocuments] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedDoc, setSelectedDoc] = useState(null);

  const fetchData = async () => {
    try {
      const [docsRes, statsRes] = await Promise.all([
        axios.get(`${API}/layer1/documents`),
        axios.get(`${API}/layer1/stats`)
      ]);
      setDocuments(docsRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error("Failed to fetch Layer 1 data:", error);
      toast.error("Failed to load official documents");
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
          <FileText className="w-12 h-12 text-zinc-600 mx-auto mb-4 animate-pulse" />
          <p className="text-zinc-500">Loading official documents...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8" data-testid="layer1-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white uppercase tracking-wide font-['Barlow_Condensed']">
            Layer 1: Official Communication Integrity
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Press releases, regulatory circulars, and public advisories analysis
          </p>
        </div>
        <button
          onClick={fetchData}
          className="btn-secondary flex items-center gap-2"
          data-testid="refresh-layer1"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className="card-tactical p-4" data-testid="stat-total-docs">
            <p className="text-xs text-zinc-500 uppercase mb-1">Total Documents</p>
            <p className="text-2xl font-bold text-white font-mono">{stats.total_documents}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-high-risk">
            <p className="text-xs text-zinc-500 uppercase mb-1">High Risk</p>
            <p className="text-2xl font-bold text-red-500 font-mono">{stats.high_risk_count}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-fabrications">
            <p className="text-xs text-zinc-500 uppercase mb-1">Fabrications</p>
            <p className="text-2xl font-bold text-amber-500 font-mono">{stats.fabrications_detected}</p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-avg-risk">
            <p className="text-xs text-zinc-500 uppercase mb-1">Avg Risk Score</p>
            <p className={`text-2xl font-bold font-mono ${getRiskColor(stats.avg_risk_score)}`}>
              {stats.avg_risk_score.toFixed(1)}
            </p>
          </div>
          <div className="card-tactical p-4" data-testid="stat-by-type">
            <p className="text-xs text-zinc-500 uppercase mb-1">By Type</p>
            <div className="flex gap-2 text-xs font-mono mt-1">
              <span className="text-blue-500">PR:{stats.by_type.press_release}</span>
              <span className="text-violet-500">RC:{stats.by_type.regulatory_circular}</span>
              <span className="text-emerald-500">PA:{stats.by_type.public_advisory}</span>
            </div>
          </div>
        </div>
      )}

      {/* Documents Table */}
      <div className="card-tactical overflow-hidden" data-testid="documents-table">
        <div className="p-4 border-b border-zinc-800">
          <h2 className="text-lg font-semibold text-white uppercase tracking-wide font-['Barlow_Condensed']">
            Analyzed Documents
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Source</th>
                <th>Risk Score</th>
                <th>Fabrication</th>
                <th>Legal Issues</th>
                <th>Overconfidence</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc, i) => (
                <motion.tr
                  key={doc.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.05 }}
                  data-testid={`doc-row-${i}`}
                >
                  <td>
                    <span className="text-xs font-mono px-2 py-1 bg-zinc-800 rounded-sm">
                      {getDocTypeIcon(doc.doc_type)}
                    </span>
                  </td>
                  <td className="max-w-xs truncate">{doc.title}</td>
                  <td className="text-zinc-400">{doc.source}</td>
                  <td>
                    <span className={`font-mono font-semibold ${getRiskColor(doc.risk_score)}`}>
                      {doc.risk_score.toFixed(1)}
                    </span>
                  </td>
                  <td>
                    {doc.fabrication_detected ? (
                      <XCircle className="w-5 h-5 text-red-500" />
                    ) : (
                      <CheckCircle className="w-5 h-5 text-emerald-500" />
                    )}
                  </td>
                  <td>
                    {doc.legal_issues.length > 0 ? (
                      <span className="badge-risk-medium">{doc.legal_issues.length} issues</span>
                    ) : (
                      <span className="badge-risk-low">None</span>
                    )}
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <div 
                          className={`h-full ${
                            doc.overconfidence_score >= 50 ? 'bg-red-500' : 
                            doc.overconfidence_score >= 25 ? 'bg-amber-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${doc.overconfidence_score}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-zinc-400">
                        {doc.overconfidence_score.toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    <button
                      onClick={() => setSelectedDoc(doc)}
                      className="p-1.5 hover:bg-zinc-700 rounded-sm transition-colors"
                      data-testid={`view-doc-${i}`}
                    >
                      <Eye className="w-4 h-4 text-zinc-400" />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Document Detail Dialog */}
      <Dialog open={!!selectedDoc} onOpenChange={() => setSelectedDoc(null)}>
        <DialogContent className="bg-zinc-900 border-zinc-800 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-white font-['Barlow_Condensed'] uppercase">
              Document Analysis
            </DialogTitle>
          </DialogHeader>
          {selectedDoc && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-white">{selectedDoc.title}</h3>
                <p className="text-sm text-zinc-400">{selectedDoc.source}</p>
              </div>
              
              <div className="grid grid-cols-3 gap-4">
                <div className="card-tactical p-3">
                  <p className="text-xs text-zinc-500 mb-1">Risk Score</p>
                  <p className={`text-xl font-bold font-mono ${getRiskColor(selectedDoc.risk_score)}`}>
                    {selectedDoc.risk_score.toFixed(1)}
                  </p>
                </div>
                <div className="card-tactical p-3">
                  <p className="text-xs text-zinc-500 mb-1">Fabrication</p>
                  <p className={`text-xl font-bold ${selectedDoc.fabrication_detected ? 'text-red-500' : 'text-emerald-500'}`}>
                    {selectedDoc.fabrication_detected ? 'DETECTED' : 'NONE'}
                  </p>
                </div>
                <div className="card-tactical p-3">
                  <p className="text-xs text-zinc-500 mb-1">Overconfidence</p>
                  <p className="text-xl font-bold font-mono text-amber-500">
                    {selectedDoc.overconfidence_score.toFixed(0)}%
                  </p>
                </div>
              </div>

              {selectedDoc.legal_issues.length > 0 && (
                <div className="card-tactical p-4">
                  <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                    <Scale className="w-4 h-4 text-amber-500" />
                    Legal Issues
                  </h4>
                  <ul className="space-y-1">
                    {selectedDoc.legal_issues.map((issue, i) => (
                      <li key={i} className="text-sm text-zinc-400 flex items-start gap-2">
                        <AlertTriangle className="w-3 h-3 text-amber-500 mt-1 flex-shrink-0" />
                        {issue}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedDoc.harmful_claims.length > 0 && (
                <div className="card-tactical p-4 border-red-500/20">
                  <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                    <XCircle className="w-4 h-4 text-red-500" />
                    Harmful Claims Detected
                  </h4>
                  <ul className="space-y-1">
                    {selectedDoc.harmful_claims.map((claim, i) => (
                      <li key={i} className="text-sm text-red-400">• {claim}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
