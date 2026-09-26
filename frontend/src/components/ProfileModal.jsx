import React, { useState, useEffect } from 'react';
import { X, Upload, User } from 'lucide-react';
import { fetchProfile, uploadResume, updateProfile } from '../services/api';

export default function ProfileModal({ isOpen, onClose, onProfileUpdated }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [newSkill, setNewSkill] = useState('');

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      fetchProfile()
        .then((data) => {
          if (data.profile) setProfile(data.profile);
        })
        .finally(() => setLoading(false));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await uploadResume(file);
      if (res.profile) {
        setProfile(res.profile);
        if (onProfileUpdated) onProfileUpdated(res.profile);
      }
    } catch (err) {
      alert('Resume extrapolation failed: ' + err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async () => {
    try {
      await updateProfile(profile);
      if (onProfileUpdated) onProfileUpdated(profile);
      onClose();
    } catch (err) {
      alert('Failed to save profile: ' + err.message);
    }
  };

  const addSkill = () => {
    if (!newSkill.trim()) return;
    const skills = profile.core_skills || [];
    if (!skills.includes(newSkill.trim())) {
      setProfile({ ...profile, core_skills: [...skills, newSkill.trim()] });
    }
    setNewSkill('');
  };

  const removeSkill = (skillToRemove) => {
    setProfile({
      ...profile,
      core_skills: (profile.core_skills || []).filter((s) => s !== skillToRemove),
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <User className="w-5 h-5 text-teal-400" />
            <h2 className="text-lg font-bold text-slate-100">Candidate Source of Truth Profile</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 text-sm">
          {/* Resume Upload Box */}
          <div className="border-2 border-dashed border-slate-700 hover:border-teal-500/80 rounded-2xl p-6 text-center transition bg-slate-950/40">
            <input
              type="file"
              id="resume-file"
              accept=".pdf,.docx,.txt"
              onChange={handleFileUpload}
              className="hidden"
            />
            <label htmlFor="resume-file" className="cursor-pointer flex flex-col items-center gap-2">
              <div className="w-12 h-12 rounded-2xl bg-teal-950/60 border border-teal-800 flex items-center justify-center text-teal-400">
                <Upload className="w-6 h-6" />
              </div>
              <p className="font-semibold text-slate-200">
                {uploading ? 'Extrapolating facts with OpenRouter LLM...' : 'Upload Resume (PDF, DOCX, TXT)'}
              </p>
              <p className="text-xs text-slate-400 max-w-sm">
                Automatically extracts technical skills, seniority level, target job titles, and experience summary.
              </p>
            </label>
          </div>

          {profile && (
            <div className="space-y-4">
              {/* Name & Seniority */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-slate-400">Full Name</label>
                  <input
                    type="text"
                    value={profile.name || ''}
                    onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                    className="w-full mt-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-sm focus:border-teal-500 outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-400">Seniority Level</label>
                  <select
                    value={profile.seniority || 'Mid'}
                    onChange={(e) => setProfile({ ...profile, seniority: e.target.value })}
                    className="w-full mt-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-sm focus:border-teal-500 outline-none"
                  >
                    <option value="Junior">Junior / Graduate</option>
                    <option value="Mid">Mid-Level</option>
                    <option value="Senior">Senior</option>
                    <option value="Lead">Lead / Principal</option>
                  </select>
                </div>
              </div>

              {/* Skills Tags */}
              <div>
                <label className="text-xs font-semibold text-slate-400">Core Technical Skills</label>
                <div className="flex gap-2 mt-1 mb-2">
                  <input
                    type="text"
                    placeholder="Add skill (e.g. AWS, Terraform, Python)..."
                    value={newSkill}
                    onChange={(e) => setNewSkill(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-200 focus:border-teal-500 outline-none"
                  />
                  <button
                    onClick={addSkill}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto p-1">
                  {(profile.core_skills || []).map((s) => (
                    <span
                      key={s}
                      className="flex items-center gap-1 text-xs px-2.5 py-1 bg-teal-950 text-teal-300 border border-teal-800/80 rounded-lg"
                    >
                      {s}
                      <button onClick={() => removeSkill(s)} className="hover:text-rose-400 ml-1">
                        &times;
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Target Salary & Locations */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-slate-400">Target Annual Salary Min ($AUD)</label>
                  <input
                    type="number"
                    value={profile.target_salary_min || ''}
                    onChange={(e) => setProfile({ ...profile, target_salary_min: parseFloat(e.target.value) || null })}
                    className="w-full mt-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-sm focus:border-teal-500 outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-400">Target Roles (Comma-separated)</label>
                  <input
                    type="text"
                    value={(profile.target_titles || []).join(', ')}
                    onChange={(e) =>
                      setProfile({
                        ...profile,
                        target_titles: e.target.value.split(',').map((t) => t.trim()).filter(Boolean),
                      })
                    }
                    className="w-full mt-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-sm focus:border-teal-500 outline-none"
                  />
                </div>
              </div>

              {/* Summary */}
              <div>
                <label className="text-xs font-semibold text-slate-400">Experience Summary</label>
                <textarea
                  rows={3}
                  value={profile.experience_summary || ''}
                  onChange={(e) => setProfile({ ...profile, experience_summary: e.target.value })}
                  className="w-full mt-1 bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-200 text-xs focus:border-teal-500 outline-none leading-relaxed"
                />
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-slate-800 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-5 py-2 bg-gradient-to-r from-teal-600 to-cyan-600 hover:from-teal-500 text-slate-950 rounded-xl text-xs font-bold shadow-md shadow-teal-950/40 transition"
          >
            Save Profile
          </button>
        </div>
      </div>
    </div>
  );
}
