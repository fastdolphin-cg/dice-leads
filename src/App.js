import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Search, LogOut, Download, RefreshCw, ChevronUp, ChevronDown, ExternalLink, Filter, X, AlertCircle, CheckCircle2, Loader2, Calendar, Clock, BarChart2, Play } from 'lucide-react';
import './App.css';

// ─── Config ───────────────────────────────────────────────────────────────────
const ALLOWED_DOMAIN = 'fastdolphin.com';
const SHEET_ID = '14Gjeh1TiJTIq0IhhAA0cKumraUy1Q0d99hmbhI1AtV8';
const APP_URL = 'https://fastdolphin-cg.github.io/dice-leads';

// ─── Auth ─────────────────────────────────────────────────────────────────────
function isValidEmail(e) { return e.toLowerCase().endsWith(`@${ALLOWED_DOMAIN}`); }
function saveSession(e) { sessionStorage.setItem('fd_user', e); }
function getSession() { return sessionStorage.getItem('fd_user'); }
function clearSession() { sessionStorage.removeItem('fd_user'); }

// ─── Google Sheets fetcher ────────────────────────────────────────────────────
const PUBLISHED_CSV = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTOiRNHYdliJrKl7AIkh6oavJgMftbtnE40MS9bOWy1L03X7qdym3-fMEz8FSSiD9Ngsy5eryFw5CYb/pub?output=csv';

async function fetchTabData(tabName) {
  // For "latest" we use the published CSV URL directly (no proxy needed)
  // For historical tabs we use gviz with proxy
  const urls = tabName === 'latest'
    ? [PUBLISHED_CSV]
    : [
        `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent(tabName)}`,
        `https://corsproxy.io/?${encodeURIComponent(`https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent(tabName)}`)}`,
      ];

  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        const csv = await res.text();
        if (csv && csv.length > 50 && !csv.toLowerCase().includes('<html')) {
          const parsed = parseCSV(csv);
          if (parsed.length > 0) return parsed;
        }
      }
    } catch (_) { continue; }
  }
  throw new Error(`Could not fetch data for: ${tabName}`);
}

async function fetchSheetTabs() {
  // Always show "Latest" as first tab, then probe for historical tabs
  const today = new Date();
  const candidates = [];
  for (let i = 0; i < 30; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const month = d.toLocaleDateString('en-US', { month: 'short' });
    const day = d.getDate();
    const year = d.getFullYear();
    candidates.push(`${month} ${String(day).padStart(2, '0')}, ${year}`);
    candidates.push(`${month} ${day}, ${year}`);
  }

  // Probe in parallel batches
  const validTabs = [];
  const seen = new Set();
  const unique = candidates.filter(c => { if (seen.has(c)) return false; seen.add(c); return true; });

  for (let i = 0; i < unique.length && validTabs.length < 7; i += 6) {
    const batch = unique.slice(i, i + 6);
    const results = await Promise.allSettled(
      batch.map(async name => { const d = await fetchTabData(name); return { name, count: d.length }; })
    );
    for (const r of results) {
      if (r.status === 'fulfilled' && r.value.count > 0) {
        validTabs.push({ title: r.value.name });
      }
    }
    if (validTabs.length >= 3 && i >= 12) break;
  }

  // Always prepend "Latest" tab which reads from published URL
  return [{ title: 'Latest' }, ...validTabs.slice(0, 6)];
}




function parseCSV(csv) {
  const lines = csv.split('\n').filter(l => l.trim());
  if (lines.length < 2) return [];
  
  const parseRow = (line) => {
    const result = [];
    let inQuotes = false;
    let current = '';
    for (let i = 0; i < line.length; i++) {
      if (line[i] === '"') {
        if (inQuotes && line[i+1] === '"') { current += '"'; i++; }
        else inQuotes = !inQuotes;
      } else if (line[i] === ',' && !inQuotes) {
        result.push(current.trim());
        current = '';
      } else {
        current += line[i];
      }
    }
    result.push(current.trim());
    return result;
  };

  const headers = parseRow(lines[0]);
  return lines.slice(1).map(line => {
    const values = parseRow(line);
    const obj = {};
    headers.forEach((h, i) => { obj[h] = values[i] || ''; });
    return obj;
  }).filter(row => row['Job Title']);
}

// ─── Login ────────────────────────────────────────────────────────────────────
function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [shaking, setShaking] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (!isValidEmail(email)) {
      setError('Access is restricted to @fastdolphin.com email addresses.');
      setShaking(true); setTimeout(() => setShaking(false), 500);
      return;
    }
    saveSession(email); onLogin(email);
  }

  return (
    <div className="login-bg">
      <div className="login-glow" />
      <div className={`login-card ${shaking ? 'shake' : ''}`}>
        <img src={`${process.env.PUBLIC_URL}/fd-logo.png`} alt="Fast Dolphin" className="login-logo-img" />
        <h1 className="login-title">Lead Finder</h1>
        <p className="login-sub">Sign in with your Fast Dolphin email to access LATAM contract leads.</p>
        <form onSubmit={handleSubmit} className="login-form">
          <input type="email" placeholder="you@fastdolphin.com" value={email}
            onChange={e => { setEmail(e.target.value); setError(''); }}
            className="login-input" autoFocus />
          {error && <div className="login-error"><AlertCircle size={14} /> {error}</div>}
          <button type="submit" className="login-btn">Continue</button>
        </form>
      </div>
    </div>
  );
}

// ─── Table ────────────────────────────────────────────────────────────────────
const COLUMNS = [
  { key: 'Job Title',       label: 'Job Title',         sortable: true  },
  { key: 'Company',         label: 'Company',           sortable: true  },
  { key: 'Location',        label: 'Location',          sortable: true  },
  { key: 'Employment Type', label: 'Employment Type',   sortable: false },
  { key: 'Work Type',       label: 'Work Type',         sortable: false },
  { key: 'Corp to Corp',    label: 'Corp to Corp',      sortable: false },
  { key: 'Pay',             label: 'Pay',               sortable: false },
  { key: 'Contract Duration', label: 'Duration',        sortable: false },
  { key: 'Keyword',         label: 'Keyword',           sortable: true  },
  { key: 'AI Reason',       label: 'Why LATAM',         sortable: false },
  { key: 'Job URL',         label: 'Link',              sortable: false },
];

function JobTable({ jobs }) {
  const [search, setSearch]     = useState('');
  const [sortCol, setSortCol]   = useState('');
  const [sortDir, setSortDir]   = useState('asc');
  const [filterKw, setFilterKw] = useState('');

  const keywords = useMemo(() => [...new Set(jobs.map(j => j['Keyword']))].filter(Boolean).sort(), [jobs]);

  const filtered = useMemo(() => {
    let rows = [...jobs];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(j =>
        (j['Job Title'] || '').toLowerCase().includes(q) ||
        (j['Company'] || '').toLowerCase().includes(q) ||
        (j['Location'] || '').toLowerCase().includes(q)
      );
    }
    if (filterKw) rows = rows.filter(j => j['Keyword'] === filterKw);
    if (sortCol) {
      rows.sort((a, b) => {
        const av = a[sortCol] || '', bv = b[sortCol] || '';
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      });
    }
    return rows;
  }, [jobs, search, sortCol, sortDir, filterKw]);

  function toggleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
  }

  function exportCSV() {
    const headers = COLUMNS.map(c => c.label);
    const rows = filtered.map(j => COLUMNS.map(c => `"${(j[c.key] || '').replace(/"/g, '""')}"`));
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `dice-leads-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }

  return (
    <div className="table-section">
      <div className="table-toolbar">
        <div className="toolbar-left">
          <div className="search-wrap">
            <Search size={14} className="search-icon" />
            <input className="search-input" placeholder="Search title, company, location…"
              value={search} onChange={e => setSearch(e.target.value)} />
            {search && <button className="search-clear" onClick={() => setSearch('')}><X size={12} /></button>}
          </div>
          {keywords.length > 0 && (
            <div className="filter-wrap">
              <Filter size={13} />
              <select className="filter-select" value={filterKw} onChange={e => setFilterKw(e.target.value)}>
                <option value="">All keywords</option>
                {keywords.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
          )}
        </div>
        <div className="toolbar-right">
          <span className="result-count">{filtered.length} lead{filtered.length !== 1 ? 's' : ''}</span>
          <button className="export-btn" onClick={exportCSV}><Download size={13} /> Export CSV</button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="leads-table">
          <thead>
            <tr>
              {COLUMNS.map(col => (
                <th key={col.key} className={col.sortable ? 'sortable' : ''}
                  onClick={col.sortable ? () => toggleSort(col.key) : undefined}>
                  {col.label}
                  {col.sortable && (sortCol === col.key
                    ? (sortDir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />)
                    : <span className="sort-idle">↕</span>)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0
              ? <tr><td colSpan={COLUMNS.length} className="empty-row">No leads match your filters.</td></tr>
              : filtered.map((job, i) => (
                <tr key={i} className="job-row">
                  <td className="col-title">{job['Job Title']}</td>
                  <td className="col-company">{job['Company']}</td>
                  <td className="col-location">{job['Location']}</td>
                  <td className="col-emptype"><span className="tag tag-blue">{job['Employment Type'] || '—'}</span></td>
                  <td>{job['Work Type'] || '—'}</td>
                  <td>{job['Corp to Corp'] || '—'}</td>
                  <td className="col-pay">{job['Pay'] || '—'}</td>
                  <td>{job['Contract Duration'] || '—'}</td>
                  <td><span className="tag tag-gold">{job['Keyword']}</span></td>
                  <td className="col-reason">{job['AI Reason'] || '—'}</td>
                  <td>
                    {job['Job URL'] ? (
                      <a href={job['Job URL']} target="_blank" rel="noopener noreferrer" className="job-link">
                        View <ExternalLink size={11} />
                      </a>
                    ) : '—'}
                  </td>
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Stats Bar ────────────────────────────────────────────────────────────────
function StatsBar({ jobs }) {
  if (!jobs.length) return null;
  return (
    <div className="stats-row">
      <div className="stat-card">
        <span className="stat-num">{jobs.length}</span>
        <span className="stat-label">Total leads</span>
      </div>
      <div className="stat-card">
        <span className="stat-num">{new Set(jobs.map(j => j['Company'])).size}</span>
        <span className="stat-label">Companies</span>
      </div>
      <div className="stat-card">
        <span className="stat-num">{new Set(jobs.map(j => j['Keyword'])).size}</span>
        <span className="stat-label">Keywords matched</span>
      </div>
      <div className="stat-card">
        <span className="stat-num">{jobs.filter(j => (j['Work Type'] || '').toLowerCase().includes('remote')).length}</span>
        <span className="stat-label">Remote roles</span>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [user, setUser]             = useState(getSession());
  const [activeTab, setActiveTab]   = useState('latest');
  const [tabs, setTabs]             = useState([]);
  const [selectedTab, setSelectedTab] = useState('');
  const [jobs, setJobs]             = useState([]);
  const [loading, setLoading]       = useState(false);
  const [loadingTabs, setLoadingTabs] = useState(false);
  const [error, setError]           = useState('');
  const [runStatus, setRunStatus]   = useState(null); // null | 'running' | 'done' | 'error'
  const [runMsg, setRunMsg]         = useState('');

  // Load available tabs on mount
  useEffect(() => {
    if (!user) return;
    loadTabs();
  }, [user]);

  async function loadTabs() {
    setLoadingTabs(true);
    try {
      const sheetTabs = await fetchSheetTabs();
      setTabs(sheetTabs);
      if (sheetTabs.length > 0) {
        setSelectedTab(sheetTabs[0].title);
        loadTabData(sheetTabs[0].title);
      }
    } catch (e) {
      setError('Could not load data: ' + e.message);
    } finally {
      setLoadingTabs(false);
    }
  }

  async function loadTabData(tabName) {
    setLoading(true);
    setError('');
    try {
      const data = await fetchTabData(tabName);
      setJobs(data);
      setSelectedTab(tabName);
    } catch (e) {
      setError('Could not load data for ' + tabName + '. ' + e.message);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }

  async function triggerScraper() {
    setRunStatus('running');
    setRunMsg('Triggering scraper… this will take 10-15 minutes to complete.');
    // We can't trigger GitHub Actions directly from a static site without a token
    // So we'll redirect the user to GitHub Actions
    setTimeout(() => {
      window.open('https://github.com/fastdolphin-cg/dice-leads/actions/workflows/scraper.yml', '_blank');
      setRunStatus('done');
      setRunMsg('GitHub Actions opened in a new tab. Click "Run workflow" to start the scraper. Results will appear here after ~15 minutes.');
    }, 500);
  }

  if (!user) return <LoginScreen onLogin={email => setUser(email)} />;

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-inner">
          <img src={`${process.env.PUBLIC_URL}/fd-logo.png`} alt="Fast Dolphin" className="header-logo" />
          <nav className="header-nav">
            <button className={`nav-btn ${activeTab === 'latest' ? 'active' : ''}`} onClick={() => setActiveTab('latest')}>
              <BarChart2 size={15} /> Latest Leads
            </button>
            <button className={`nav-btn ${activeTab === 'history' ? 'active' : ''}`} onClick={() => setActiveTab('history')}>
              <Calendar size={15} /> History
            </button>
            <button className={`nav-btn ${activeTab === 'run' ? 'active' : ''}`} onClick={() => setActiveTab('run')}>
              <Play size={15} /> Run Scraper
            </button>
          </nav>
          <div className="header-right">
            <span className="header-user">{user}</span>
            <button className="logout-btn" onClick={() => { clearSession(); setUser(null); }} title="Sign out">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* Latest Leads Tab */}
      {activeTab === 'latest' && (
        <div className="tab-content">
          <div className="tab-hero">
            <div className="tab-hero-text">
              <div className="tab-eyebrow">Dice.com · Last 3 days · Contract & Third Party · AI Verified</div>
              <h2 className="tab-title">LATAM Lead Finder</h2>
              <p className="tab-sub">
                {tabs.length > 0 ? `Showing results from ${tabs[0]?.title === 'Latest' ? 'today\'s scrape' : tabs[0]?.title}` : 'Loading latest results…'}
              </p>
            </div>
            <button className="refresh-btn" onClick={() => tabs[0] && loadTabData(tabs[0].title)} disabled={loading}>
              {loading ? <><Loader2 size={15} className="spin" /> Loading…</> : <><RefreshCw size={15} /> Refresh</>}
            </button>
          </div>

          {error && <div className="error-bar"><AlertCircle size={14} /> {error}</div>}

          {loading ? (
            <div className="loading-state"><Loader2 size={32} className="spin" /><p>Loading leads…</p></div>
          ) : (
            <>
              <StatsBar jobs={jobs} />
              <main className="main-content">
                {jobs.length > 0 ? <JobTable jobs={jobs} /> : (
                  <div className="empty-state">
                    <img src={`${process.env.PUBLIC_URL}/fd-logo.png`} alt="" className="empty-logo" />
                    <p className="empty-title">No leads for this date</p>
                    <p className="empty-desc">Try selecting a different date in the History tab, or run the scraper to pull fresh leads.</p>
                  </div>
                )}
              </main>
            </>
          )}
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="tab-content">
          <div className="tab-hero">
            <div className="tab-hero-text">
              <div className="tab-eyebrow">Up to 7 most recent runs</div>
              <h2 className="tab-title">Run History</h2>
              <p className="tab-sub">Select any date to view that day's leads.</p>
            </div>
          </div>

          <div className="history-grid">
            {loadingTabs ? (
              <div className="loading-state"><Loader2 size={32} className="spin" /><p>Loading history…</p></div>
            ) : tabs.length === 0 ? (
              <div className="empty-state">
                <p className="empty-title">No runs yet</p>
                <p className="empty-desc">Run the scraper to start building history.</p>
              </div>
            ) : (
              tabs.map(tab => (
                <button key={tab.title} className={`history-card ${selectedTab === tab.title ? 'active' : ''}`}
                  onClick={() => { loadTabData(tab.title); setActiveTab('latest'); }}>
                  <Calendar size={20} className="history-icon" />
                  <span className="history-date">{tab.title}</span>
                  <span className="history-action">View leads →</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* Run Scraper Tab */}
      {activeTab === 'run' && (
        <div className="tab-content">
          <div className="tab-hero">
            <div className="tab-hero-text">
              <div className="tab-eyebrow">Manual trigger</div>
              <h2 className="tab-title">Run Scraper</h2>
              <p className="tab-sub">The scraper runs automatically every day at 8AM Eastern. Use this to trigger a manual run.</p>
            </div>
          </div>

          <div className="run-section">
            <div className="run-card">
              <div className="run-info">
                <div className="run-schedule">
                  <Clock size={18} />
                  <div>
                    <div className="run-schedule-label">Automatic schedule</div>
                    <div className="run-schedule-value">Every day at 8:00 AM Eastern</div>
                  </div>
                </div>
                <div className="run-details">
                  <div className="run-detail-item"><span>Keywords</span><span>16 LATAM keywords</span></div>
                  <div className="run-detail-item"><span>Filter</span><span>Contract & Third Party only</span></div>
                  <div className="run-detail-item"><span>Date range</span><span>Last 3 days</span></div>
                  <div className="run-detail-item"><span>AI verification</span><span>Claude Haiku</span></div>
                  <div className="run-detail-item"><span>Duration</span><span>~10-15 minutes</span></div>
                  <div className="run-detail-item"><span>Notification</span><span>Email on completion</span></div>
                </div>
              </div>

              <div className="run-action">
                <button className={`run-btn ${runStatus === 'running' ? 'running' : ''}`}
                  onClick={triggerScraper} disabled={runStatus === 'running'}>
                  {runStatus === 'running'
                    ? <><Loader2 size={18} className="spin" /> Opening GitHub Actions…</>
                    : <><Play size={18} /> Run Now</>}
                </button>

                {runStatus === 'done' && (
                  <div className="run-status done">
                    <CheckCircle2 size={16} /> {runMsg}
                  </div>
                )}
                {runStatus === 'error' && (
                  <div className="run-status error">
                    <AlertCircle size={16} /> {runMsg}
                  </div>
                )}
                {!runStatus && (
                  <p className="run-note">Clicking "Run Now" will open GitHub Actions in a new tab where you can trigger the scraper with one click.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <footer className="app-footer">
        Fast Dolphin Consulting Group · Internal use only · {new Date().getFullYear()}
      </footer>
    </div>
  );
}
