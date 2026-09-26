import React, { useState, useEffect } from 'react';
import { Sparkles, User, Briefcase, Kanban, LogIn } from 'lucide-react';
import { fetchStudioModels, googleLogin } from '../services/api';

export default function Header({ activeTab, setActiveTab, onOpenProfile, selectedModel, setSelectedModel }) {
  const [models, setModels] = useState([]);
  const [userName, setUserName] = useState(localStorage.getItem('user_name') || 'Candidate');

  useEffect(() => {
    fetchStudioModels()
      .then((data) => {
        if (data.models) {
          setModels(data.models);
          if (!selectedModel && data.default_model) {
            setSelectedModel(data.default_model);
          }
        }
      })
      .catch((err) => console.warn('Could not load models:', err));
  }, []);

  const handleSimulateGoogleLogin = async () => {
    try {
      const mockCredential = `mock_gis_${Date.now()}`;
      const res = await googleLogin(mockCredential);
      if (res.token) {
        localStorage.setItem('token', res.token);
        localStorage.setItem('user_id', res.user.id);
        localStorage.setItem('user_name', res.user.name);
        setUserId(res.user.id);
        setUserName(res.user.name);
        window.location.reload();
      }
    } catch (err) {
      alert('Mock GIS login failed: ' + err.message);
    }
  };

  return (
    <header className="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Logo & Title */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-teal-400 flex items-center justify-center shadow-lg shadow-teal-950/40">
            <Briefcase className="w-5 h-5 text-slate-950" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg text-slate-100 tracking-tight">Job Dashboard</span>
              <span className="px-1.5 py-0.5 text-xs font-semibold bg-teal-950 text-teal-400 border border-teal-800/80 rounded-md">
                LIGHT
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">Australian Career Studio & Job Aggregator</p>
          </div>
        </div>

        {/* Tab Navigation */}
        <nav className="flex items-center bg-slate-950/60 p-1 rounded-xl border border-slate-800/80 text-sm">
          <button
            onClick={() => setActiveTab('discovery')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-medium transition ${
              activeTab === 'discovery'
                ? 'bg-slate-800 text-teal-400 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Briefcase className="w-4 h-4" />
            <span>Discover Jobs</span>
          </button>
          <button
            onClick={() => setActiveTab('tracker')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-medium transition ${
              activeTab === 'tracker'
                ? 'bg-slate-800 text-teal-400 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Kanban className="w-4 h-4" />
            <span>Kanban Tracker</span>
          </button>
        </nav>

        {/* Action Controls & User */}
        <div className="flex items-center gap-3">
          {/* Model Selector Dropdown */}
          <div className="hidden md:flex items-center gap-1.5 bg-slate-950/60 px-2.5 py-1.5 rounded-xl border border-slate-800/80 text-xs">
            <Sparkles className="w-3.5 h-3.5 text-teal-400" />
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-transparent text-slate-200 outline-none cursor-pointer pr-1 font-medium"
            >
              {models.length > 0 ? (
                models.map((m) => (
                  <option key={m.id} value={m.id} className="bg-slate-900 text-slate-200">
                    {m.name} ({m.provider})
                  </option>
                ))
              ) : (
                <option value="deepseek/deepseek-chat" className="bg-slate-900 text-slate-200">
                  DeepSeek V3
                </option>
              )}
            </select>
          </div>

          {/* Profile & GIS Button */}
          <button
            onClick={onOpenProfile}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/80 hover:bg-slate-800 text-slate-200 border border-slate-700/60 rounded-xl text-xs font-semibold transition"
          >
            <User className="w-3.5 h-3.5 text-teal-400" />
            <span className="truncate max-w-[120px]">{userName}</span>
          </button>

          <button
            onClick={handleSimulateGoogleLogin}
            title="Google Identity Sign-In (One-click GIS demo)"
            className="p-1.5 bg-slate-800/60 hover:bg-slate-800 text-slate-400 hover:text-teal-300 border border-slate-800 rounded-xl transition"
          >
            <LogIn className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
