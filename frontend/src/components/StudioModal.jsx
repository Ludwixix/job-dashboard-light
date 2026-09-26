import React, { useState } from 'react';
import { X, Sparkles, Download, Copy, Check, FileText, Send, ShieldCheck } from 'lucide-react';
import { generateStudioDocument } from '../services/api';

export default function StudioModal({ isOpen, onClose, job, selectedModel }) {
  const [docType, setDocType] = useState('cv'); // 'cv', 'cover_letter', 'ksc'
  const [variant, setVariant] = useState('systems_architect');
  const [framework, setFramework] = useState('APS');
  const [wordLimit, setWordLimit] = useState(350);
  const [generating, setGenerating] = useState(false);
  const [resultDoc, setResultDoc] = useState(null);
  const [copied, setCopied] = useState(false);

  if (!isOpen || !job) return null;

  const handleGenerate = async () => {
    setGenerating(true);
    setResultDoc(null);
    try {
      const payload = {
        model: selectedModel || 'deepseek/deepseek-chat',
        doc_type: docType,
        job_id: job.id,
        job_title: job.title,
        company: job.company,
        location: job.location,
        job_description: job.description || `${job.title} at ${job.company}`,
        variant,
        framework,
        target_word_limit: wordLimit,
        user_id: localStorage.getItem('user_id') || 'usr_default',
      };
      const res = await generateStudioDocument(payload);
      if (res.content_markdown) {
        setResultDoc(res);
      }
    } catch (err) {
      alert('Generation error: ' + err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyMarkdown = () => {
    if (!resultDoc?.content_markdown) return;
    navigator.clipboard.writeText(resultDoc.content_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadPdf = async () => {
    if (!resultDoc?.content_markdown) return;
    try {
      const res = await fetch('/api/studio/export/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: resultDoc.title || `${job.title} - Application`,
          content_markdown: resultDoc.content_markdown,
          document_id: resultDoc.document_id,
        }),
      });
      if (!res.ok) throw new Error('PDF export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${resultDoc.title || 'document'}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert('PDF export failed: ' + err.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-teal-400" />
            <div>
              <h2 className="text-base font-bold text-slate-100">Bespoke Application Studio</h2>
              <p className="text-xs text-slate-400">
                {job.title} — <span className="text-teal-400">{job.company}</span>
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Studio Controls */}
        <div className="px-6 py-3 bg-slate-950/60 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Doc Type Selector */}
          <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setDocType('cv')}
              className={`px-3 py-1 rounded-lg font-semibold transition ${
                docType === 'cv' ? 'bg-teal-950 text-teal-300 border border-teal-800' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              ATS Resume / CV
            </button>
            <button
              onClick={() => setDocType('cover_letter')}
              className={`px-3 py-1 rounded-lg font-semibold transition ${
                docType === 'cover_letter' ? 'bg-teal-950 text-teal-300 border border-teal-800' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Polarized Cover Letter
            </button>
            <button
              onClick={() => setDocType('ksc')}
              className={`px-3 py-1 rounded-lg font-semibold transition ${
                docType === 'ksc' ? 'bg-teal-950 text-teal-300 border border-teal-800' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Australian KSC (STAR)
            </button>
          </div>

          {/* Type-Specific Options */}
          <div className="flex items-center gap-2">
            {docType === 'cover_letter' && (
              <select
                value={variant}
                onChange={(e) => setVariant(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 font-medium"
              >
                <option value="systems_architect">Systems Architect Variant</option>
                <option value="cultural_outlier">Cultural Outlier Variant</option>
                <option value="contrarian_specialist">Contrarian Specialist</option>
              </select>
            )}

            {docType === 'ksc' && (
              <div className="flex items-center gap-2">
                <select
                  value={framework}
                  onChange={(e) => setFramework(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-slate-200 font-medium"
                >
                  <option value="APS">APS ILS Framework</option>
                  <option value="VPSC">VPSC Capability Framework</option>
                </select>
                <input
                  type="number"
                  value={wordLimit}
                  onChange={(e) => setWordLimit(parseInt(e.target.value) || 350)}
                  className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-slate-200"
                  title="Word limit per criterion"
                />
              </div>
            )}

            <button
              onClick={handleGenerate}
              disabled={generating}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-gradient-to-r from-teal-600 to-cyan-600 hover:from-teal-500 text-slate-950 rounded-xl font-bold transition shadow-sm"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{generating ? 'Generating...' : 'Synthesize'}</span>
            </button>
          </div>
        </div>

        {/* Content Body / Preview */}
        <div className="flex-1 p-6 overflow-y-auto bg-slate-950/30">
          {resultDoc ? (
            <div className="space-y-4">
              {/* Anti-Template Score Banner (for cover letters) */}
              {resultDoc.anti_template_passed !== undefined && (
                <div className="flex items-center justify-between p-3 bg-emerald-950/40 border border-emerald-800 rounded-xl text-xs text-emerald-300">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <span>Anti-Template Engine: Passed cliché audit with 0 generic openers.</span>
                  </div>
                  <span className="font-bold">Swappability Risk: {resultDoc.swappability_score}% (Low)</span>
                </div>
              )}

              {/* Markdown Display Box */}
              <div className="p-6 bg-slate-900 border border-slate-800 rounded-2xl text-slate-200 font-mono text-xs whitespace-pre-wrap leading-relaxed select-text shadow-inner">
                {resultDoc.content_markdown}
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-400">
              <FileText className="w-12 h-12 text-slate-700 mb-3" />
              <p className="font-semibold text-slate-300 text-sm">Select options and click "Synthesize"</p>
              <p className="text-xs text-slate-500 max-w-md mt-1">
                Generates ATS-grounded application documents in Australian English tailored specifically to this job posting.
              </p>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-800 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            Powered by {selectedModel || 'OpenRouter'}
          </span>

          <div className="flex items-center gap-3">
            <button
              onClick={handleCopyMarkdown}
              disabled={!resultDoc}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-750 disabled:opacity-40 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold transition"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-teal-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied!' : 'Copy Markdown'}</span>
            </button>

            <button
              onClick={handleDownloadPdf}
              disabled={!resultDoc}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-slate-800 hover:bg-slate-750 disabled:opacity-40 text-teal-300 border border-teal-800/80 rounded-xl text-xs font-semibold transition"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download PDF</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
