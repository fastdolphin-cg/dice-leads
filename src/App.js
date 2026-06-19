import React, { useState, useEffect, useMemo } from 'react';
import { Search, LogOut, Download, RefreshCw, ChevronUp, ChevronDown, ExternalLink, Filter, X, AlertCircle, CheckCircle2, Loader2, Fish } from 'lucide-react';
import './App.css';

// ─── Config ───────────────────────────────────────────────────────────────────
const ALLOWED_DOMAIN = 'fastdolphin.com';

const LATAM_KEYWORDS = [
  'mexico', 'brazil', 'brasil', 'colombia', 'argentina', 'chile',
  'latin america', 'spanish', 'latam', 'bolivia', 'peru',
  'costa rica', 'panama', 'ecuador', 'portuguese', 'maquiladora'
];

const TARGET_EMPLOYMENT_TYPES = ['contract', 'third party', 'corp to corp', 'c2c', 'third-party'];

const DICE_API_BASE = 'https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search';

// ─── Auth helpers ─────────────────────────────────────────────────────────────
function isValidEmail(email) {
  return email.toLowerCase().endsWith(`@${ALLOWED_DOMAIN}`);
}

function saveSession(email) {
  sessionStorage.setItem('fd_user', email);
}

function getSession() {
  return sessionStorage.getItem('fd_user');
}

function clearSession() {
  sessionStorage.removeItem('fd_user');
}

// ─── Dice scrape logic ────────────────────────────────────────────────────────
async function fetchDiceJobs(keyword, page = 1) {
  const params = new URLSearchParams({
    q: keyword,
    countryCode: 'US',
    radius: '30',
    radiusUnit: 'mi',
    page: String(page),
    pageSize: '20',
    facets: 'employmentType|postedDate|workFromHomeAvailability|employerType|easyApply|isUnderrated',
    filters: 'postedDate|THREE',
    cleanJobTitle: keyword,
    unemployment: 'false',
  });

  const res = await fetch(`${DICE_API_BASE}?${params.toString()}`, {
    headers: {
      'x-api-key': 'yRExoMhXAb4cPEGZ', // Dice public web key (no auth required)
      'content-type': 'application/json',
    },
  });

  if (!res.ok) throw new Error(`Dice API error: ${res.status}`);
  const data = await res.json();
  return data;
}

function jobMatchesFilters(job) {
  const text = [
    job.jobDescription || '',
    job.employmentType || '',
    job.employerType || '',
    job.location || '',
    job.title || '',
  ].join(' ').toLowerCase();

  const hasLatam = LATAM_KEYWORDS.some(kw => text.includes(kw));
  const hasContract = TARGET_EMPLOYMENT_TYPES.some(et => text.includes(et));

  return hasLatam && hasContract;
}

function buildJobRow(job, keyword) {
  return {
    id: job.id || job.jobId || Math.random().toString(36).slice(2),
    title: job.title || '',
    company: job.hiringOrganization?.name || job.advertiserName || '',
    location: job.location || '',
    employmentType: job.employmentType || '',
    employerType: job.employerType || '',
    workType: job.workFromHomeAvailability || '',
    pay: job.salary || '',
    postedDate: job.datePosted || job.date || '',
    description: job.jobDescription ? job.jobDescription.replace(/<[^>]+>/g, '').slice(0, 200) + '…' : '',
    url: job.applyDataItem?.externalApplyLink || `https://www.dice.com/jobs/detail/${job.id}`,
    keyword,
  };
}

// ─── Components ───────────────────────────────────────────────────────────────

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [shaking, setShaking] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (!isValidEmail(email)) {
      setError('Access is restricted to @fastdolphin.com email addresses.');
      setShaking(true);
      setTimeout(() => setShaking(false), 500);
      return;
    }
    saveSession(email);
    onLogin(email);
  }

  return (
    <div className="login-bg">
      <div className="login-glow" />
      <div className={`login-card ${shaking ? 'shake' : ''}`}>
        <div className="login-logo">
          <Fish size={32} className="login-fish" />
          <span className="login-brand">Fast Dolphin</span>
        </div>
        <h1 className="login-title">Lead Finder</h1>
        <p className="login-sub">Sign in with your Fast Dolphin email to access LATAM contract leads from Dice.</p>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="input-group">
            <input
              type="email"
              placeholder="you@fastdolphin.com"
              value={email}
              onChange={e => { setEmail(e.target.value); setError(''); }}
              className="login-input"
              autoFocus
            />
          </div>
          {error && (
            <div className="login-error">
              <AlertCircle size={14} /> {error}
            </div>
          )}
          <button type="submit" className="login-btn">
            Continue
          </button>
        </form>
      </div>
    </div>
  );
}

function StatusBar({ status, progress }) {
  if (!status) return null;
  const isRunning = status === 'running';
  const isDone = status === 'done';
  const isError = status === 'error';

  return (
    <div className={`status-bar ${status}`}>
      {isRunning && <Loader2 size={14} className="spin" />}
      {isDone && <CheckCircle2 size={14} />}
      {isError && <AlertCircle size={14} />}
      <span className="status-text">{progress}</span>
    </div>
  );
}

function SortIcon({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <span className="sort-idle">↕</span>;
  return sortDir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />;
}

const COLUMNS = [
  { key: 'title', label: 'Job Title', sortable: true },
  { key: 'company', label: 'Company', sortable: true },
  { key: 'location', label: 'Location', sortable: true },
  { key: 'employmentType', label: 'Employment Type', sortable: false },
  { key: 'employerType', label: 'Employer Type', sortable: false },
  { key: 'workType', label: 'Work Type', sortable: false },
  { key: 'pay', label: 'Pay', sortable: false },
  { key: 'postedDate', label: 'Posted', sortable: true },
  { key: 'keyword', label: 'Keyword', sortable: true },
  { key: 'url', label: 'Link', sortable: false },
];

function JobTable({ jobs }) {
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState('postedDate');
  const [sortDir, setSortDir] = useState('desc');
  const [filterType, setFilterType] = useState('');

  const employmentTypes = useMemo(() => {
    const types = new Set(jobs.map(j => j.employmentType).filter(Boolean));
    return [...types];
  }, [jobs]);

  const filtered = useMemo(() => {
    let rows = [...jobs];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(j =>
        j.title.toLowerCase().includes(q) ||
        j.company.toLowerCase().includes(q) ||
        j.location.toLowerCase().includes(q) ||
        j.keyword.toLowerCase().includes(q)
      );
    }
    if (filterType) {
      rows = rows.filter(j => j.employmentType === filterType);
    }
    if (sortCol) {
      rows.sort((a, b) => {
        const av = a[sortCol] || '';
        const bv = b[sortCol] || '';
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      });
    }
    return rows;
  }, [jobs, search, sortCol, sortDir, filterType]);

  function toggleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
  }

  function exportCSV() {
    const headers = COLUMNS.map(c => c.label);
    const rows = filtered.map(j => COLUMNS.map(c => `"${(j[c.key] || '').replace(/"/g, '""')}"`));
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dice-leads-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }

  return (
    <div className="table-section">
      <div className="table-toolbar">
        <div className="toolbar-left">
          <div className="search-wrap">
            <Search size={14} className="search-icon" />
            <input
              className="search-input"
              placeholder="Search title, company, location…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && <button className="search-clear" onClick={() => setSearch('')}><X size={12} /></button>}
          </div>
          {employmentTypes.length > 0 && (
            <div className="filter-wrap">
              <Filter size={13} />
              <select className="filter-select" value={filterType} onChange={e => setFilterType(e.target.value)}>
                <option value="">All employment types</option>
                {employmentTypes.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          )}
        </div>
        <div className="toolbar-right">
          <span className="result-count">{filtered.length} lead{filtered.length !== 1 ? 's' : ''}</span>
          <button className="export-btn" onClick={exportCSV}>
            <Download size={13} /> Export CSV
          </button>
        </div>
      </div>

      <div className="table-wrap">
        <table className="leads-table">
          <thead>
            <tr>
              {COLUMNS.map(col => (
                <th
                  key={col.key}
                  className={col.sortable ? 'sortable' : ''}
                  onClick={col.sortable ? () => toggleSort(col.key) : undefined}
                >
                  {col.label}
                  {col.sortable && <SortIcon col={col.key} sortCol={sortCol} sortDir={sortDir} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={COLUMNS.length} className="empty-row">No leads match your filters.</td></tr>
            ) : (
              filtered.map(job => (
                <tr key={job.id} className="job-row">
                  <td className="col-title">{job.title}</td>
                  <td className="col-company">{job.company}</td>
                  <td className="col-location">{job.location}</td>
                  <td><span className="tag tag-blue">{job.employmentType || '—'}</span></td>
                  <td><span className="tag tag-teal">{job.employerType || '—'}</span></td>
                  <td>{job.workType || '—'}</td>
                  <td className="col-pay">{job.pay || '—'}</td>
                  <td className="col-date">{job.postedDate ? new Date(job.postedDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}</td>
                  <td><span className="tag tag-gold">{job.keyword}</span></td>
                  <td>
                    <a href={job.url} target="_blank" rel="noopener noreferrer" className="job-link">
                      View <ExternalLink size={11} />
                    </a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [user, setUser] = useState(getSession());
  const [scrapeStatus, setScrapeStatus] = useState(null); // null | 'running' | 'done' | 'error'
  const [progress, setProgress] = useState('');
  const [jobs, setJobs] = useState([]);
  const [lastRun, setLastRun] = useState(null);

  useEffect(() => {
    const saved = localStorage.getItem('fd_jobs');
    const savedTime = localStorage.getItem('fd_last_run');
    if (saved) { try { setJobs(JSON.parse(saved)); } catch (_) {} }
    if (savedTime) setLastRun(new Date(savedTime));
  }, []);

  async function runScrape() {
    setScrapeStatus('running');
    setJobs([]);
    const found = [];
    const seen = new Set();

    try {
      for (let i = 0; i < LATAM_KEYWORDS.length; i++) {
        const kw = LATAM_KEYWORDS[i];
        setProgress(`Searching "${kw}" (${i + 1} of ${LATAM_KEYWORDS.length})…`);

        for (let page = 1; page <= 2; page++) {
          try {
            const data = await fetchDiceJobs(kw, page);
            const hits = data.data || data.jobs || [];
            if (hits.length === 0) break;

            for (const job of hits) {
              const jobId = job.id || job.jobId;
              if (seen.has(jobId)) continue;
              if (!jobMatchesFilters(job)) continue;
              seen.add(jobId);
              found.push(buildJobRow(job, kw));
            }
          } catch (err) {
            console.warn(`Page ${page} for "${kw}" failed:`, err.message);
            break;
          }
          await new Promise(r => setTimeout(r, 300));
        }
      }

      const now = new Date();
      setJobs(found);
      setLastRun(now);
      localStorage.setItem('fd_jobs', JSON.stringify(found));
      localStorage.setItem('fd_last_run', now.toISOString());
      setScrapeStatus('done');
      setProgress(`Found ${found.length} LATAM contract lead${found.length !== 1 ? 's' : ''} from the last 3 days.`);
    } catch (err) {
      setScrapeStatus('error');
      setProgress(`Something went wrong: ${err.message}`);
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
  }

  if (!user) {
    return <LoginScreen onLogin={email => setUser(email)} />;
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-inner">
          <div className="header-brand">
            <Fish size={22} className="header-fish" />
            <div>
              <span className="header-name">Fast Dolphin</span>
              <span className="header-sep">·</span>
              <span className="header-product">Lead Finder</span>
            </div>
          </div>
          <div className="header-right">
            <span className="header-user">{user}</span>
            <button className="logout-btn" onClick={handleLogout} title="Sign out">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* Hero / Controls */}
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-text">
            <h2 className="hero-title">LATAM Contract Leads</h2>
            <p className="hero-sub">
              Jobs posted on Dice in the last 3 days matching Latin America keywords and contract employment types.
              {lastRun && <span className="last-run"> Last pull: {lastRun.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>}
            </p>
          </div>
          <button
            className={`scrape-btn ${scrapeStatus === 'running' ? 'running' : ''}`}
            onClick={runScrape}
            disabled={scrapeStatus === 'running'}
          >
            {scrapeStatus === 'running'
              ? <><Loader2 size={16} className="spin" /> Pulling leads…</>
              : <><RefreshCw size={16} /> Pull fresh leads</>
            }
          </button>
        </div>
        <StatusBar status={scrapeStatus} progress={progress} />
      </section>

      {/* Stats row */}
      {jobs.length > 0 && (
        <div className="stats-row">
          <div className="stat-card">
            <span className="stat-num">{jobs.length}</span>
            <span className="stat-label">Total leads</span>
          </div>
          <div className="stat-card">
            <span className="stat-num">{new Set(jobs.map(j => j.company)).size}</span>
            <span className="stat-label">Companies</span>
          </div>
          <div className="stat-card">
            <span className="stat-num">{new Set(jobs.map(j => j.keyword)).size}</span>
            <span className="stat-label">Keywords matched</span>
          </div>
          <div className="stat-card">
            <span className="stat-num">{jobs.filter(j => (j.workType || '').toLowerCase().includes('remote')).length}</span>
            <span className="stat-label">Remote roles</span>
          </div>
        </div>
      )}

      {/* Table */}
      <main className="main-content">
        {jobs.length > 0 ? (
          <JobTable jobs={jobs} />
        ) : (
          <div className="empty-state">
            <Fish size={40} className="empty-fish" />
            <p className="empty-title">No leads yet</p>
            <p className="empty-desc">Click "Pull fresh leads" to search Dice for LATAM contract opportunities.</p>
          </div>
        )}
      </main>

      <footer className="app-footer">
        Fast Dolphin · Internal use only · {new Date().getFullYear()}
      </footer>
    </div>
  );
}
