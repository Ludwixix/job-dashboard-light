/**
 * REST API Client for Job Dashboard Light
 */

function getAuthHeaders() {
  const token = localStorage.getItem('token');
  const userId = localStorage.getItem('user_id') || 'usr_default';
  const headers = {
    'Content-Type': 'application/json',
    'X-User-Id': userId,
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export async function fetchJobs(params = {}) {
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.location && params.location !== 'All Australia') query.set('location', params.location);
  if (params.source && params.source !== 'All') query.set('source', params.source);
  if (params.min_salary) query.set('min_salary', params.min_salary);
  if (params.max_age_days) query.set('max_age_days', params.max_age_days);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.page) query.set('page', params.page);
  query.set('user_id', localStorage.getItem('user_id') || 'usr_default');

  const res = await fetch(`/api/jobs?${query.toString()}`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch jobs (${res.status})`);
  return res.json();
}

export async function fetchJobDetails(jobId) {
  const userId = localStorage.getItem('user_id') || 'usr_default';
  const res = await fetch(`/api/jobs/${jobId}?user_id=${userId}`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch job details (${res.status})`);
  return res.json();
}

export async function triggerScrape(term, location = 'All Australia', force = false) {
  const res = await fetch('/api/scrape', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ term, location, force }),
  });
  if (!res.ok) throw new Error(`Failed to trigger scraper (${res.status})`);
  return res.json();
}

export async function fetchProfile() {
  const res = await fetch('/api/profile', {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch candidate profile (${res.status})`);
  return res.json();
}

export async function uploadResume(file) {
  const formData = new FormData();
  formData.append('file', file);
  const token = localStorage.getItem('token');
  const userId = localStorage.getItem('user_id') || 'usr_default';
  const headers = { 'X-User-Id': userId };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch('/api/profile/upload', {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!res.ok) throw new Error(`Resume upload failed (${res.status})`);
  return res.json();
}

export async function updateProfile(profileData) {
  const res = await fetch('/api/profile', {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(profileData),
  });
  if (!res.ok) throw new Error(`Profile update failed (${res.status})`);
  return res.json();
}

export async function fetchApplications() {
  const res = await fetch('/api/applications', {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch applications (${res.status})`);
  return res.json();
}

export async function trackApplication(jobId, status = 'Draft', notes = '') {
  const res = await fetch('/api/applications', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ job_id: jobId, status, notes }),
  });
  if (!res.ok) throw new Error(`Failed to track job application (${res.status})`);
  return res.json();
}

export async function updateApplicationStage(appId, patchData) {
  const res = await fetch(`/api/applications/${appId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(patchData),
  });
  if (!res.ok) throw new Error(`Failed to update application (${res.status})`);
  return res.json();
}

export async function deleteApplication(appId) {
  const res = await fetch(`/api/applications/${appId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to delete application (${res.status})`);
  return res.json();
}

export async function fetchStudioModels() {
  const res = await fetch('/api/studio/models', {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch model presets (${res.status})`);
  return res.json();
}

export async function generateStudioDocument(payload) {
  const res = await fetch('/api/studio/generate', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Document generation failed (${res.status})`);
  return res.json();
}

export async function googleLogin(credential) {
  const res = await fetch('/api/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  });
  if (!res.ok) throw new Error(`Login failed (${res.status})`);
  return res.json();
}
