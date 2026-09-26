import React, { useState } from 'react';
import { updateApplicationStage, deleteApplication } from '../services/api';
import { Trash2, Calendar, FileText, UserCheck, Sparkles } from 'lucide-react';

const STAGES = ['Draft', 'Applied', 'Interviewing', 'Offered', 'Rejected'];

const STAGE_COLORS = {
  Draft: 'border-slate-700 bg-slate-900/50 text-slate-300',
  Applied: 'border-blue-800/80 bg-blue-950/20 text-blue-300',
  Interviewing: 'border-amber-800/80 bg-amber-950/20 text-amber-300',
  Offered: 'border-emerald-800/80 bg-emerald-950/20 text-emerald-300',
  Rejected: 'border-rose-900/60 bg-rose-950/20 text-rose-400',
};

export default function KanbanBoard({ board, onRefresh, onOpenStudio }) {
  const [editingAppId, setEditingAppId] = useState(null);
  const [editNotes, setEditNotes] = useState('');
  const [editInterviewDate, setEditInterviewDate] = useState('');
  const [editRecruiter, setEditRecruiter] = useState('');

  const handleStageChange = async (appId, newStatus) => {
    try {
      await updateApplicationStage(appId, { status: newStatus });
      onRefresh();
    } catch (err) {
      alert('Failed to update stage: ' + err.message);
    }
  };

  const handleDelete = async (appId) => {
    if (!confirm('Remove this application from tracker?')) return;
    try {
      await deleteApplication(appId);
      onRefresh();
    } catch (err) {
      alert('Failed to delete application: ' + err.message);
    }
  };

  const handleSaveDetails = async (appId) => {
    try {
      await updateApplicationStage(appId, {
        notes: editNotes,
        interview_at: editInterviewDate || null,
        recruiter_name: editRecruiter || null,
      });
      setEditingAppId(null);
      onRefresh();
    } catch (err) {
      alert('Failed to save details: ' + err.message);
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {STAGES.map((stage) => {
        const cards = board[stage] || [];
        return (
          <div key={stage} className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col min-h-[500px]">
            {/* Column Header */}
            <div className={`flex items-center justify-between px-3 py-2 rounded-xl border mb-3 font-semibold text-xs ${STAGE_COLORS[stage]}`}>
              <span>{stage}</span>
              <span className="px-2 py-0.5 rounded-full bg-slate-950/60 text-xs font-bold">
                {cards.length}
              </span>
            </div>

            {/* Cards List */}
            <div className="flex-1 space-y-3 overflow-y-auto">
              {cards.map((app) => (
                <div
                  key={app.id}
                  className="bg-slate-950/90 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 shadow-sm transition flex flex-col justify-between gap-3 text-xs"
                >
                  <div>
                    <h4 className="font-bold text-slate-100 line-clamp-1">{app.job_title}</h4>
                    <p className="text-teal-400 font-medium mt-0.5">{app.job_company}</p>
                    <p className="text-slate-400 mt-1">{app.job_location || 'All Australia'}</p>

                    {/* Interview date badge */}
                    {app.interview_at && (
                      <div className="mt-2 flex items-center gap-1 text-amber-400 font-medium">
                        <Calendar className="w-3.5 h-3.5" />
                        <span>{app.interview_at.split('T')[0]}</span>
                      </div>
                    )}

                    {/* Recruiter info */}
                    {app.recruiter_name && (
                      <div className="mt-1 flex items-center gap-1 text-slate-400">
                        <UserCheck className="w-3.5 h-3.5" />
                        <span>{app.recruiter_name}</span>
                      </div>
                    )}

                    {/* Notes preview */}
                    {app.notes && editingAppId !== app.id && (
                      <p className="mt-2 text-slate-400 italic line-clamp-2 bg-slate-900/60 p-1.5 rounded-lg border border-slate-800/80">
                        "{app.notes}"
                      </p>
                    )}

                    {/* Inline Editor */}
                    {editingAppId === app.id && (
                      <div className="mt-3 space-y-2 p-2 bg-slate-900 rounded-lg border border-slate-700">
                        <div>
                          <label className="text-[10px] text-slate-400">Interview Date:</label>
                          <input
                            type="date"
                            value={editInterviewDate}
                            onChange={(e) => setEditInterviewDate(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-200 text-xs"
                          />
                        </div>
                        <div>
                          <label className="text-[10px] text-slate-400">Recruiter Contact:</label>
                          <input
                            type="text"
                            placeholder="Name / Email"
                            value={editRecruiter}
                            onChange={(e) => setEditRecruiter(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-200 text-xs"
                          />
                        </div>
                        <div>
                          <label className="text-[10px] text-slate-400">Notes:</label>
                          <textarea
                            rows={2}
                            value={editNotes}
                            onChange={(e) => setEditNotes(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-200 text-xs"
                          />
                        </div>
                        <div className="flex gap-2 justify-end">
                          <button
                            onClick={() => setEditingAppId(null)}
                            className="px-2 py-1 text-slate-400 hover:text-slate-200 text-xs"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleSaveDetails(app.id)}
                            className="px-2.5 py-1 bg-teal-600 text-slate-950 rounded font-bold text-xs"
                          >
                            Save
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Stage Switcher & Actions */}
                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-1">
                    <select
                      value={app.status}
                      onChange={(e) => handleStageChange(app.id, e.target.value)}
                      className="bg-slate-900 border border-slate-700/80 rounded px-1.5 py-1 text-[11px] text-slate-200 outline-none"
                    >
                      {STAGES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>

                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => {
                          setEditingAppId(app.id);
                          setEditNotes(app.notes || '');
                          setEditInterviewDate(app.interview_at ? app.interview_at.split('T')[0] : '');
                          setEditRecruiter(app.recruiter_name || '');
                        }}
                        title="Edit Details & Interview Dates"
                        className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded"
                      >
                        <FileText className="w-3.5 h-3.5" />
                      </button>

                      <button
                        onClick={() => onOpenStudio({
                          id: app.job_id,
                          title: app.job_title,
                          company: app.job_company,
                          location: app.job_location,
                          description: '',
                        })}
                        title="Open in Studio"
                        className="p-1 hover:bg-slate-800 text-teal-400 rounded"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                      </button>

                      <button
                        onClick={() => handleDelete(app.id)}
                        title="Delete Card"
                        className="p-1 hover:bg-slate-800 text-rose-400 rounded"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
