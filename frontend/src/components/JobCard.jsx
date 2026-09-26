import React from 'react';
import { ExternalLink, MapPin, DollarSign, Sparkles, PlusCircle, CheckCircle } from 'lucide-react';

export default function JobCard({ job, onOpenStudio, onTrack, isTracked }) {
  const getScoreColor = (score) => {
    if (!score && score !== 0) return 'bg-slate-800 text-slate-400 border-slate-700';
    if (score >= 80) return 'bg-emerald-950 text-emerald-300 border-emerald-800';
    if (score >= 60) return 'bg-teal-950 text-teal-300 border-teal-800';
    if (score >= 40) return 'bg-amber-950 text-amber-300 border-amber-800';
    return 'bg-rose-950 text-rose-300 border-rose-800';
  };

  const getSourceBadge = (source) => {
    const s = (source || '').toLowerCase();
    if (s.includes('seek')) return 'bg-rose-950 text-rose-400 border-rose-800/80';
    if (s.includes('linkedin')) return 'bg-sky-950 text-sky-400 border-sky-800/80';
    if (s.includes('aps')) return 'bg-purple-950 text-purple-300 border-purple-800/80';
    if (s.includes('vic')) return 'bg-indigo-950 text-indigo-300 border-indigo-800/80';
    return 'bg-slate-800 text-slate-300 border-slate-700';
  };

  return (
    <div className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-2xl p-5 shadow-sm transition hover:shadow-md flex flex-col justify-between gap-4">
      <div>
        {/* Top Badges */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs px-2.5 py-0.5 rounded-full border font-semibold ${getSourceBadge(job.source)}`}>
              {job.source || 'Aggregator'}
            </span>
            {job.posted_age_days !== undefined && job.posted_age_days !== null && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700/60">
                {job.posted_age_days === 0 ? 'Today' : `${job.posted_age_days}d ago`}
              </span>
            )}
            {job.closing_date && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-950/60 text-amber-400 border border-amber-800/60">
                Closes: {job.closing_date.split('T')[0]}
              </span>
            )}
          </div>

          {/* Match Score Badge */}
          {job.match_score !== null && job.match_score !== undefined && (
            <div className={`flex items-center gap-1 px-2.5 py-1 rounded-xl border text-xs font-bold ${getScoreColor(job.match_score)}`}>
              <Sparkles className="w-3.5 h-3.5" />
              <span>{Math.round(job.match_score)}%</span>
            </div>
          )}
        </div>

        {/* Title & Company */}
        <h3 className="text-base font-bold text-slate-100 leading-snug line-clamp-2">
          {job.title}
        </h3>
        <p className="text-sm font-medium text-teal-400 mt-1">{job.company}</p>

        {/* Meta Info */}
        <div className="mt-3 flex flex-wrap items-center gap-y-1.5 gap-x-4 text-xs text-slate-400">
          <div className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-slate-500" />
            <span>{job.location || 'All Australia'}</span>
          </div>
          {job.salary_raw && (
            <div className="flex items-center gap-1 text-emerald-400 font-medium">
              <DollarSign className="w-3.5 h-3.5 text-emerald-500" />
              <span>{job.salary_raw}</span>
            </div>
          )}
        </div>

        {/* Matched & Missing Skills */}
        {job.matched_skills?.length > 0 && (
          <div className="mt-3 flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400 font-medium">Matched:</span>
            {job.matched_skills.slice(0, 4).map((s, idx) => (
              <span key={idx} className="text-[10px] px-2 py-0.5 bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 rounded-md font-medium">
                {s}
              </span>
            ))}
          </div>
        )}

        {/* Short description preview */}
        <p className="mt-3 text-xs text-slate-400 line-clamp-3 leading-relaxed">
          {job.description?.replace(/<[^>]*>?/gm, '')}
        </p>
      </div>

      {/* Action Footer */}
      <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between gap-2">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition font-medium"
        >
          <span>View on Portal</span>
          <ExternalLink className="w-3 h-3" />
        </a>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onTrack(job)}
            disabled={isTracked}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition border ${
              isTracked
                ? 'bg-slate-800 text-teal-400 border-slate-700 cursor-default'
                : 'bg-slate-800 hover:bg-slate-750 text-slate-200 border-slate-700/80'
            }`}
          >
            {isTracked ? <CheckCircle className="w-3.5 h-3.5 text-teal-400" /> : <PlusCircle className="w-3.5 h-3.5" />}
            <span>{isTracked ? 'Tracked' : 'Track'}</span>
          </button>

          <button
            onClick={() => onOpenStudio(job)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-teal-600 to-cyan-600 hover:from-teal-500 hover:to-cyan-500 text-slate-950 rounded-xl text-xs font-bold shadow-md shadow-teal-950/40 transition"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Studio</span>
          </button>
        </div>
      </div>
    </div>
  );
}
