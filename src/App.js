import React, { useState, useEffect, useMemo } from 'react';
import { Search, LogOut, Download, RefreshCw, ChevronUp, ChevronDown, ExternalLink, Filter, X, AlertCircle, CheckCircle2, Loader2, Clock, BarChart2, Play } from 'lucide-react';
import './App.css';

// ─── Config ───────────────────────────────────────────────────────────────────
const ALLOWED_DOMAIN = 'fastdolphin.com';
const BASE_URL = `${window.location.origin}${process.env.PUBLIC_URL}`;
const GH_TOKEN = process.env.REACT_APP_GH_TOKEN;
const GH_OWNER = 'fastdolphin-cg';
const GH_REPO = 'dice-leads';
const GH_WORKFLOW = 'scraper.yml';

// ─── Auth ─────────────────────────────────────────────────────────────────────
function isValidEmail(e) { return e.toLowerCase().endsWith(`@${ALLOWED_DOMAIN}`); }
function saveSession(e) { sessionStorage.setItem('fd_user', e); }
function getSession() { return sessionStorage.getItem('fd_user'); }
function clearSession() { sessionStorage.removeItem('fd_user'); }

// ─── Data fetchers ────────────────────────────────────────────────────────────
async function fetchLatest() {
  const res = await fetch(`${BASE_URL}/data/latest.json?t=${Date.now()}`);
  if (!res.ok) throw new Error('No data available yet. Run the scraper first.');
  return res.json();
}

async function triggerGitHubWorkflow(inputs = {}) {
  const res = await fetch(
    `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/actions/workflows/${GH_WORKFLOW}/dispatches`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${GH_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main', inputs }),
    }
  );
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`GitHub API error ${res.status}: ${err}`);
  }
  return true;
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
  { key: 'Run Date',          label: 'Run Date',    sortable: true,  width: '100px' },
  { key: 'Job Title',         label: 'Job Title',   sortable: true,  width: '180px' },
  { key: 'Company',           label: 'Company',     sortable: true,  width: '140px' },
  { key: 'Location',          label: 'Location',    sortable: true,  width: '130px' },
  { key: 'Employment Type',   label: 'Emp. Type',   sortable: false, width: '320px' },
  { key: 'Work Type',         label: 'Work',        sortable: true,  width: '90px'  },
  { key: 'Corp to Corp',      label: 'C2C',         sortable: false, width: '140px' },
  { key: 'Contract Duration', label: 'Duration',    sortable: false, width: '80px'  },
  { key: 'Pay',               label: 'Pay',         sortable: true,  width: '110px' },
  { key: 'Posted Date',       label: 'Posted',      sortable: true,  width: '100px' },
  { key: 'Keyword',           label: 'Keyword',     sortable: true,  width: '90px'  },
  { key: 'AI Reason',         label: 'Why LATAM',   sortable: false, width: '260px' },
  { key: 'Job URL',           label: '',            sortable: false, width: '40px'  },
];

function JobTable({ jobs }) {
  const [search, setSearch]       = useState('');
  const [sortCol, setSortCol]     = useState('Run Date');
  const [sortDir, setSortDir]     = useState('desc');
  const [filters, setFilters]     = useState({});

  // Get unique values for each filterable column
  const filterOptions = useMemo(() => {
    const opts = {};
    ['Work Type', 'Keyword', 'Location', 'Posted Date'].forEach(col => {
      opts[col] = [...new Set(jobs.map(j => j[col]).filter(Boolean))].sort();
    });
    return opts;
  }, [jobs]);

  const filtered = useMemo(() => {
    let rows = [...jobs];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(j =>
        (j['Job Title'] || '').toLowerCase().includes(q) ||
        (j['Company'] || '').toLowerCase().includes(q) ||
        (j['Location'] || '').toLowerCase().includes(q) ||
        (j['Employment Type'] || '').toLowerCase().includes(q)
      );
    }
    Object.entries(filters).forEach(([col, val]) => {
      if (val) rows = rows.filter(j => j[col] === val);
    });
    if (sortCol) {
      rows.sort((a, b) => {
        const av = a[sortCol] || '', bv = b[sortCol] || '';
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      });
    }
    return rows;
  }, [jobs, search, sortCol, sortDir, filters]);

  function toggleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
  }

  function setFilter(col, val) {
    setFilters(prev => ({ ...prev, [col]: val }));
  }

  function exportCSV() {
    const headers = COLUMNS.filter(c => c.key !== 'Job URL').map(c => c.label || c.key);
    headers.push('Job URL');
    const rows = filtered.map(j => [
      ...COLUMNS.filter(c => c.key !== 'Job URL').map(c => `"${(j[c.key] || '').replace(/"/g, '""')}"`),
      `"${j['Job URL'] || ''}"`
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `dice-leads-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }

  const activeFilters = Object.values(filters).filter(Boolean).length;

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
          {/* Column filters */}
          {Object.entries(filterOptions).map(([col, options]) => (
            <div key={col} className="filter-wrap">
              <Filter size={12} />
              <select className="filter-select" value={filters[col] || ''}
                onChange={e => setFilter(col, e.target.value)}>
                <option value="">{col}</option>
                {options.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          ))}
          {activeFilters > 0 && (
            <button className="clear-filters" onClick={() => setFilters({})}>
              <X size={12} /> Clear filters
            </button>
          )}
        </div>
        <div className="toolbar-right">
          <span className="result-count">{filtered.length} lead{filtered.length !== 1 ? 's' : ''}</span>
          <button className="export-btn" onClick={exportCSV}><Download size={13} /> Export CSV</button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="leads-table">
          <colgroup>
            {COLUMNS.map(col => <col key={col.key} style={{width: col.width}} />)}
          </colgroup>
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
                  <td className="col-rundate">
                    <div className="rundate-date">{job['Run Date'] || '—'}</div>
                    <div className="rundate-time">{job['Run Time'] || ''}</div>
                  </td>
                  <td className="col-title">{job['Job Title']}</td>
                  <td className="col-company">{job['Company']}</td>
                  <td className="col-location">{job['Location']}</td>
                  <td><span className="tag tag-blue">{job['Employment Type'] || '—'}</span></td>
                  <td>{job['Work Type'] || '—'}</td>
                  <td>{job['Corp to Corp'] || '—'}</td>
                  <td>{job['Contract Duration'] || '—'}</td>
                  <td className="col-pay">{job['Pay'] || '—'}</td>
                  <td className="col-posted">{job['Posted Date'] || '—'}</td>
                  <td><span className="tag tag-gold">{job['Keyword']}</span></td>
                  <td className="col-reason">{job['AI Reason'] || '—'}</td>
                  <td className="col-link">
                    {job['Job URL'] ? (
                      <a href={job['Job URL']} target="_blank" rel="noopener noreferrer" className="job-link-icon" title="View job">
                        <ExternalLink size={14} />
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
        <span className="stat-label">Keywords</span>
      </div>
      <div className="stat-card">
        <span className="stat-num">{jobs.filter(j => (j['Work Type'] || '').toLowerCase().includes('remote')).length}</span>
        <span className="stat-label">Remote roles</span>
      </div>
    </div>
  );
}

// ─── Run Scraper Tab ──────────────────────────────────────────────────────────
const DEFAULT_KEYWORDS = [
  'mexico','spanish','brazil','brasil','argentina','colombia',
  'ecuador','costa rica','panama','portuguese','latam',
  'latin america','maquiladora','chile','bolivia','peru',
];

const EMPLOYMENT_OPTIONS = [
  { id: 'CONTRACTS', label: 'Contract W2' },
  { id: 'THIRD_PARTY', label: 'Third Party' },
  { id: 'CONTRACT_INDEPENDENT', label: 'Contract Independent' },
  { id: 'FULLTIME', label: 'Full Time' },
  { id: 'PARTTIME', label: 'Part Time' },
];

function RunScraperTab() {
  const [stdStatus, setStdStatus] = useState(null);
  const [stdMsg, setStdMsg]       = useState('');
  const [keywords, setKeywords]   = useState([...DEFAULT_KEYWORDS]);
  const [newKw, setNewKw]         = useState('');
  const [empTypes, setEmpTypes]   = useState(['CONTRACTS','THIRD_PARTY','CONTRACT_INDEPENDENT']);
  const [dateRange, setDateRange] = useState(2);
  const [aiModel, setAiModel]     = useState('haiku');
  const [sendEmail, setSendEmail] = useState(true);
  const [showSonnetWarn, setShowSonnetWarn] = useState(false);
  const [modStatus, setModStatus] = useState(null);
  const [modMsg, setModMsg]       = useState('');

  async function runStandard() {
    setStdStatus('running'); setStdMsg('');
    try {
      await triggerGitHubWorkflow({});
      setStdStatus('done');
      setStdMsg('Scraper started! Results will appear in ~15 minutes.');
    } catch (e) { setStdStatus('error'); setStdMsg(e.message); }
  }

  async function runModified() {
    setModStatus('running'); setModMsg('');
    try {
      await triggerGitHubWorkflow({
        keywords: keywords.join(','),
        employment_types: empTypes.join('|'),
        date_range: String(dateRange),
        ai_model: aiModel,
        send_email: String(sendEmail),
        run_label: 'Modified Run',
      });
      setModStatus('done');
      setModMsg('Modified scrape started! Results will appear in ~15 minutes.');
    } catch (e) { setModStatus('error'); setModMsg(e.message); }
  }

  function toggleKw(kw) {
    setKeywords(prev => prev.includes(kw) ? prev.filter(k => k !== kw) : [...prev, kw]);
  }
  function addKw() {
    const k = newKw.trim().toLowerCase();
    if (k && !keywords.includes(k)) setKeywords(prev => [...prev, k]);
    setNewKw('');
  }
  function toggleEmp(id) {
    setEmpTypes(prev => prev.includes(id) ? prev.filter(e => e !== id) : [...prev, id]);
  }

  return (
    <div className="tab-content">
      <div className="tab-hero">
        <div className="tab-hero-text">
          <div className="tab-eyebrow">Manual trigger</div>
          <h2 className="tab-title">Run Scraper</h2>
          <p className="tab-sub">Runs automatically at 8:00 AM and 3:30 PM Eastern. Use the buttons below for a manual run.</p>
        </div>
      </div>
      <div className="run-panels">
        {/* Standard Run */}
        <div className="run-card">
          <div className="run-card-header">
            <div className="run-card-title">Standard Run</div>
            <div className="run-card-sub">Default settings · ~15 min</div>
          </div>
          <div className="run-info">
            <div className="run-schedule">
              <Clock size={16} />
              <div>
                <div className="run-schedule-label">Automatic schedule</div>
                <div className="run-schedule-value">8:00 AM & 3:30 PM Eastern</div>
              </div>
            </div>
            <div className="run-details">
              <div className="run-detail-item"><span>Keywords</span><span>16 LATAM keywords</span></div>
              <div className="run-detail-item"><span>Employment type</span><span>Contract, Third Party & Independent</span></div>
              <div className="run-detail-item"><span>Date range</span><span>Last 2 days</span></div>
              <div className="run-detail-item"><span>AI model</span><span>Claude Haiku</span></div>
              <div className="run-detail-item"><span>Notification</span><span>Email on completion</span></div>
            </div>
          </div>
          <div className="run-action">
            <button className={`run-btn ${stdStatus === 'running' ? 'running' : ''}`}
              onClick={runStandard} disabled={stdStatus === 'running' || modStatus === 'running'}>
              {stdStatus === 'running' ? <><Loader2 size={16} className="spin" /> Starting…</> : <><Play size={16} /> Run Now</>}
            </button>
            {stdStatus === 'done' && <div className="run-status done"><CheckCircle2 size={14} /> {stdMsg}</div>}
            {stdStatus === 'error' && <div className="run-status error"><AlertCircle size={14} /> {stdMsg}</div>}
          </div>
        </div>

        {/* Modified Run */}
        <div className="run-card run-card-modified">
          <div className="run-card-header">
            <div className="run-card-title">Modified Run</div>
            <div className="run-card-sub">Custom settings · one-time only</div>
          </div>
          <div className="run-info">
            <div className="mod-section">
              <div className="mod-label">Keywords</div>
              <div className="kw-chips">
                {DEFAULT_KEYWORDS.map(kw => (
                  <button key={kw} className={`kw-chip ${keywords.includes(kw) ? 'active' : 'inactive'}`} onClick={() => toggleKw(kw)}>
                    {kw} {keywords.includes(kw) ? '×' : '+'}
                  </button>
                ))}
                {keywords.filter(k => !DEFAULT_KEYWORDS.includes(k)).map(kw => (
                  <button key={kw} className="kw-chip active custom" onClick={() => toggleKw(kw)}>{kw} ×</button>
                ))}
              </div>
              <div className="kw-add">
                <input className="kw-input" placeholder="Add keyword…" value={newKw}
                  onChange={e => setNewKw(e.target.value)} onKeyDown={e => e.key === 'Enter' && addKw()} />
                <button className="kw-add-btn" onClick={addKw}>Add</button>
              </div>
            </div>
            <div className="mod-section">
              <div className="mod-label">Employment Type</div>
              <div className="check-group">
                {EMPLOYMENT_OPTIONS.map(opt => (
                  <label key={opt.id} className="check-item">
                    <input type="checkbox" checked={empTypes.includes(opt.id)} onChange={() => toggleEmp(opt.id)} />
                    <span>{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="mod-section">
              <div className="mod-label">Date Range — Last <strong>{dateRange}</strong> day{dateRange !== 1 ? 's' : ''}</div>
              <input type="range" min="1" max="30" value={dateRange}
                onChange={e => setDateRange(Number(e.target.value))} className="date-slider" />
              <div className="date-slider-labels"><span>1 day</span><span>30 days</span></div>
            </div>
            <div className="mod-section">
              <div className="mod-label">AI Model</div>
              <div className="radio-group">
                <label className="radio-item">
                  <input type="radio" name="model" checked={aiModel === 'haiku'} onChange={() => setAiModel('haiku')} />
                  <span>Claude Haiku <em>(fast, ~$0.001/job)</em></span>
                </label>
                <label className="radio-item">
                  <input type="radio" name="model" checked={aiModel === 'sonnet'} onChange={() => { if (aiModel !== 'sonnet') setShowSonnetWarn(true); }} />
                  <span>Claude Sonnet 4.6 <em>(smarter, ~$0.01/job)</em></span>
                </label>
              </div>
            </div>
            <div className="mod-section">
              <div className="mod-label">Notification</div>
              <div className="radio-group">
                <label className="radio-item">
                  <input type="radio" name="notify" checked={sendEmail} onChange={() => setSendEmail(true)} />
                  <span>Email on completion</span>
                </label>
                <label className="radio-item">
                  <input type="radio" name="notify" checked={!sendEmail} onChange={() => setSendEmail(false)} />
                  <span>No email — results in app only</span>
                </label>
              </div>
            </div>
          </div>
          <div className="run-action">
            <button className={`run-btn run-btn-modified ${modStatus === 'running' ? 'running' : ''}`}
              onClick={runModified} disabled={modStatus === 'running' || stdStatus === 'running' || keywords.length === 0 || empTypes.length === 0}>
              {modStatus === 'running' ? <><Loader2 size={16} className="spin" /> Starting…</> : <><Play size={16} /> Run Modified Scrape</>}
            </button>
            {modStatus === 'done' && <div className="run-status done"><CheckCircle2 size={14} /> {modMsg}</div>}
            {modStatus === 'error' && <div className="run-status error"><AlertCircle size={14} /> {modMsg}</div>}
          </div>
        </div>
      </div>

      {showSonnetWarn && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-title">⚠️ Higher Cost Warning</div>
            <p className="modal-body">Claude Sonnet 4.6 is approximately <strong>10× more expensive</strong> than Haiku (~$0.01 per job vs ~$0.001). Are you sure?</p>
            <div className="modal-actions">
              <button className="modal-btn-cancel" onClick={() => setShowSonnetWarn(false)}>Cancel — keep Haiku</button>
              <button className="modal-btn-confirm" onClick={() => { setAiModel('sonnet'); setShowSonnetWarn(false); }}>Yes, use Sonnet</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [user, setUser]         = useState(getSession());
  const [activeTab, setActiveTab] = useState('latest');
  const [jobs, setJobs]         = useState([]);
  const [scrapedAt, setScrapedAt] = useState('');
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  useEffect(() => {
    if (!user) return;
    loadLatest();
  }, [user]);

  async function loadLatest() {
    setLoading(true); setError('');
    try {
      const data = await fetchLatest();
      setJobs(data.jobs || []);
      setScrapedAt(data.scraped_at_eastern || data.scraped_at || '');
    } catch (e) {
      setError(e.message); setJobs([]);
    } finally {
      setLoading(false);
    }
  }

  const formattedScrapedAt = scrapedAt || '';

  if (!user) return <LoginScreen onLogin={email => setUser(email)} />;

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <img src={`${process.env.PUBLIC_URL}/fd-logo.png`} alt="Fast Dolphin" className="header-logo" />
          <nav className="header-nav">
            <button className={`nav-btn ${activeTab === 'latest' ? 'active' : ''}`} onClick={() => setActiveTab('latest')}>
              <BarChart2 size={15} /> All Leads
            </button>
            <button className={`nav-btn ${activeTab === 'run' ? 'active' : ''}`} onClick={() => setActiveTab('run')}>
              <Play size={15} /> Run Scraper
            </button>
            <button className={`nav-btn ${activeTab === 'prompt' ? 'active' : ''}`} onClick={() => setActiveTab('prompt')}>
              <Filter size={15} /> AI Prompt
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

      {activeTab === 'latest' && (
        <div className="tab-content">
          <div className="tab-hero">
            <div className="tab-hero-text">
              <div className="tab-eyebrow">Dice.com · Contract & Third Party & Independent · AI Verified · No duplicates · Last 30 days</div>
              <h2 className="tab-title">LATAM Lead Finder</h2>
              <p className="tab-sub">
                All verified leads, newest first.
                {formattedScrapedAt && <span className="last-run"> Last updated: {formattedScrapedAt}</span>}
              </p>
            </div>
            <button className="refresh-btn" onClick={loadLatest} disabled={loading}>
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
                  !error && (
                    <div className="empty-state">
                      <img src={`${process.env.PUBLIC_URL}/fd-logo.png`} alt="" className="empty-logo" />
                      <p className="empty-title">No leads yet</p>
                      <p className="empty-desc">Run the scraper to pull fresh LATAM contract leads from Dice.</p>
                    </div>
                  )
                )}
              </main>
            </>
          )}
        </div>
      )}

      {activeTab === 'run' && <RunScraperTab />}

      {activeTab === 'prompt' && (
        <div className="tab-content">
          <div className="tab-hero">
            <div className="tab-hero-text">
              <div className="tab-eyebrow">Read only · For reference</div>
              <h2 className="tab-title">AI Filter Prompt</h2>
              <p className="tab-sub">This is the exact prompt sent to Claude Haiku to evaluate each job posting.</p>
            </div>
          </div>
          <div className="prompt-section">
            <div className="prompt-card">
              <div className="prompt-header">
                <div className="prompt-header-text">
                  <h3>LATAM Job Relevance Evaluator</h3>
                  <p>Model: Claude Haiku 4.5 · Called once per job posting · ~$0.001 per call</p>
                </div>
                <span className="prompt-badge">claude-haiku-4-5</span>
              </div>
              <div className="prompt-body">{`You are a strict recruiting analyst. Your job is to decide if a job posting has a GENUINE Latin America connection meaning the actual job requirements, candidate location, or language skills involve Latin America.

STEP 1: Read the ENTIRE job description carefully.

STEP 2: Understand the nature of the job description and decide if it is related with Latin America or Spanish/Portuguese language. The following is a partial list of keywords: Latin America, Mexico, Brazil, Colombia, Argentina, Chile, Peru, Ecuador, Costa Rica, Panama, Bolivia, LATAM, Maquiladora, Spanish, or Portuguese. If the job mentions any other Latin American country not listed here (such as Paraguay, Uruguay, Venezuela, Honduras, Guatemala, Nicaragua, Dominican Republic, etc.), please include it, as long as it is under the context explained in this prompt.

STEP 3: For EACH mention, determine its context.

AUTOMATICALLY REJECT - answer NO - if Latin America, Spanish, Portuguese, or any related keyword ONLY appears in:
- Email signature or footer listing office locations such as "USA | CANADA | Mexico | INDIA"
- Company boilerplate like "we have offices in..." or "presence in..." or "internationally in..."
- Equal opportunity employment statements
- The US state of New Mexico
- The word "Perl" (programming language) — this is NOT "Peru"
- Recruiter contact information or company address
- Phrases describing where the COMPANY operates, NOT where the CANDIDATE works

ACCEPT - answer YES - ONLY if Latin America, Spanish, Portuguese, or any related keyword appears in:
- The actual job requirements (e.g. "must be bilingual", "Spanish required", "based in Mexico City")
- The candidate work location (e.g. "position located in Bogota", "remote from LATAM")
- Required skills or experience (e.g. "LATAM market experience", "serve Latin American clients")
- Language requirements (e.g. "fluent Spanish", "Portuguese required", "bilingual English/Spanish")
- The role description itself mentioning LATAM work or clients
- Any Latin American country in the context of the job requirement (not just a company office mention)

CONCRETE EXAMPLES:
- "USA | CANADA | Mexico | INDIA" in footer = NO
- "offices in Mexico City and India" = NO
- "PruTech has nearshore offices in Mexico City" but job is in Brooklyn NY = NO
- "Must be fluent in Spanish" = YES
- "Position based in Guadalajara" = YES
- "Bilingual English/Spanish required" = YES
- "Nearshore delivery from Mexico" = YES
- "Experience working with teams in Paraguay" = YES`}
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
