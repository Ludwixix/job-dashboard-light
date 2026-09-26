import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import JobCard from './components/JobCard';
import KanbanBoard from './components/KanbanBoard';
import StudioModal from './components/StudioModal';
import ProfileModal from './components/ProfileModal';
import SafeErrorBoundary from './components/SafeErrorBoundary';
import { fetchJobs, fetchApplications, trackApplication, triggerScrape } from './services/api';
import { Search, RefreshCw, Briefcase } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('discovery'); // 'discovery' | 'tracker'
  const [selectedModel, setSelectedModel] = useState('deepseek/deepseek-chat');

  // Jobs state
  const [jobs, setJobs] = useState([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [sources, setSources] = useState([]);
  const [searchTerm, setSearchTerm] = useState('Cloud Engineer');
  const [selectedLocation, setSelectedLocation] = useState('All Australia');
  const [selectedSource, setSelectedSource] = useState('All');
  const [minSalary, setMinSalary] = useState('');
  const [sortBy, setSortBy] = useState('posted_date');
  const [scraping, setScraping] = useState(false);

  // Kanban state
  const [board, setBoard] = useState({
    Draft: [],
    Applied: [],
    Interviewing: [],
    Offered: [],
    Rejected: [],
  });
  const [trackedJobIds, setTrackedJobIds] = useState(new Set());

  // Modals state
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [isStudioOpen, setIsStudioOpen] = useState(false);
  const [activeStudioJob, setActiveStudioJob] = useState(null);

  const loadJobs = async () => {
    setLoadingJobs(true);
    try {
      const data = await fetchJobs({
        q: searchTerm,
        location: selectedLocation,
        source: selectedSource,
        min_salary: minSalary ? parseFloat(minSalary) : undefined,
        sort_by: sortBy,
      });
      setJobs(data.jobs || []);
      setTotalJobs(data.total || 0);
      if (data.sources) setSources(data.sources);
    } catch (err) {
      console.error('Failed to load jobs:', err);
    } finally {
      setLoadingJobs(false);
    }
  };

  const loadBoard = async () => {
    try {
      const data = await fetchApplications();
      if (data.board) {
        setBoard(data.board);
        const ids = new Set((data.applications || []).map((a) => a.job_id));
        setTrackedJobIds(ids);
      }
    } catch (err) {
      console.error('Failed to load board:', err);
    }
  };

  useEffect(() => {
    loadJobs();
    loadBoard();
  }, [sortBy, selectedSource, selectedLocation]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadJobs();
  };

  const handleTriggerScraper = async () => {
    setScraping(true);
    try {
      await triggerScrape(searchTerm || 'Software Engineer', selectedLocation, true);
      await loadJobs();
    } catch (err) {
      alert('Scraper triggered with error: ' + err.message);
    } finally {
      setScraping(false);
    }
  };

  const handleTrackJob = async (job) => {
    try {
      await trackApplication(job.id, 'Draft', `Added from Discovery on ${new Date().toLocaleDateString()}`);
      await loadBoard();
    } catch (err) {
      alert('Failed to track job: ' + err.message);
    }
  };

  const handleOpenStudio = (job) => {
    setActiveStudioJob(job);
    setIsStudioOpen(true);
  };

  return (
    <SafeErrorBoundary>
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
        <Header
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          onOpenProfile={() => setIsProfileOpen(true)}
          selectedModel={selectedModel}
          setSelectedModel={setSelectedModel}
        />

        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {activeTab === 'discovery' ? (
            <div className="space-y-6">
              {/* Search & Ingestion Bar */}
              <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-sm space-y-4">
                <form onSubmit={handleSearchSubmit} className="flex flex-wrap items-center gap-3">
                  <div className="flex-1 min-w-[240px] relative">
                    <Search className="w-4 h-4 absolute left-3.5 top-3.5 text-slate-400" />
                    <input
                      type="text"
                      placeholder="Search roles (e.g. Systems Engineer, SRE, Cloud)..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-2xl pl-10 pr-4 py-2.5 text-sm text-slate-100 outline-none transition"
                    />
                  </div>

                  <select
                    value={selectedLocation}
                    onChange={(e) => setSelectedLocation(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-2xl px-3.5 py-2.5 text-sm text-slate-200 outline-none"
                  >
                    <option value="All Australia">All Australia</option>
                    <option value="Sydney">Sydney, NSW</option>
                    <option value="Melbourne">Melbourne, VIC</option>
                    <option value="Brisbane">Brisbane, QLD</option>
                    <option value="Canberra">Canberra, ACT</option>
                    <option value="Remote">Remote</option>
                  </select>

                  <select
                    value={selectedSource}
                    onChange={(e) => setSelectedSource(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-2xl px-3.5 py-2.5 text-sm text-slate-200 outline-none"
                  >
                    <option value="All">All Portals</option>
                    <option value="Seek">Seek</option>
                    <option value="APS Jobs">APS Jobs</option>
                    <option value="Careers Vic">Careers Vic</option>
                    <option value="LinkedIn">LinkedIn</option>
                    <option value="Indeed">Indeed</option>
                    <option value="Adzuna">Adzuna</option>
                  </select>

                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-2xl px-3.5 py-2.5 text-sm text-slate-200 outline-none"
                  >
                    <option value="posted_date">Newest Posted</option>
                    <option value="match">Highest Match Score</option>
                    <option value="salary">Highest Salary</option>
                  </select>

                  <button
                    type="submit"
                    className="px-5 py-2.5 bg-gradient-to-r from-teal-600 to-cyan-600 hover:from-teal-500 text-slate-950 rounded-2xl font-bold text-sm transition shadow-sm"
                  >
                    Search
                  </button>

                  <button
                    type="button"
                    onClick={handleTriggerScraper}
                    disabled={scraping}
                    title="Coalesced Real-time Australian Scraper Coordinator"
                    className="flex items-center gap-1.5 px-4 py-2.5 bg-slate-800 hover:bg-slate-750 text-teal-300 border border-teal-800/80 rounded-2xl text-xs font-semibold transition"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${scraping ? 'animate-spin' : ''}`} />
                    <span>{scraping ? 'Scraping Portals...' : 'Sync Scrapers'}</span>
                  </button>
                </form>

                {/* Sub-bar stats */}
                <div className="flex items-center justify-between text-xs text-slate-400 px-1 pt-1 border-t border-slate-800/60">
                  <span>Found {totalJobs} active Australian opportunities</span>
                  <span>Coalesced DB-first priority • Single-flight concurrency</span>
                </div>
              </div>

              {/* Jobs Grid */}
              {loadingJobs ? (
                <div className="flex flex-col items-center justify-center p-16 text-slate-400">
                  <RefreshCw className="w-8 h-8 animate-spin text-teal-400 mb-3" />
                  <p className="text-sm font-medium">Querying local SQLite WAL index & FTS5 search...</p>
                </div>
              ) : jobs.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                  {jobs.map((job) => (
                    <JobCard
                      key={job.id}
                      job={job}
                      onOpenStudio={handleOpenStudio}
                      onTrack={handleTrackJob}
                      isTracked={trackedJobIds.has(job.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-12 text-center text-slate-400">
                  <Briefcase className="w-12 h-12 text-slate-700 mx-auto mb-3" />
                  <h3 className="text-base font-bold text-slate-200">No matching jobs found</h3>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto mt-1 mb-4">
                    Try broadening your search term or click "Sync Scrapers" to scrape active Australian postings.
                  </p>
                  <button
                    onClick={handleTriggerScraper}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-teal-300 border border-teal-800/80 rounded-xl text-xs font-semibold"
                  >
                    Trigger Australian Scraper Coordinator
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-100">Application Pipeline Kanban</h2>
                  <p className="text-xs text-slate-400">Organize and monitor candidate stages, interview dates, and notes.</p>
                </div>
                <button
                  onClick={loadBoard}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Refresh</span>
                </button>
              </div>

              <KanbanBoard
                board={board}
                onRefresh={loadBoard}
                onOpenStudio={handleOpenStudio}
              />
            </div>
          )}
        </main>

        {/* Studio Modal */}
        <StudioModal
          isOpen={isStudioOpen}
          onClose={() => setIsStudioOpen(false)}
          job={activeStudioJob}
          selectedModel={selectedModel}
        />

        {/* Profile Modal */}
        <ProfileModal
          isOpen={isProfileOpen}
          onClose={() => setIsProfileOpen(false)}
          onProfileUpdated={() => loadJobs()}
        />
      </div>
    </SafeErrorBoundary>
  );
}
