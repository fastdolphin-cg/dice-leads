import React, { useState, useEffect, useMemo } from 'react';
import { Search, LogOut, Download, RefreshCw, ChevronUp, ChevronDown, ExternalLink, Filter, X, AlertCircle, CheckCircle2, Loader2, Calendar, Clock, BarChart2, Play } from 'lucide-react';
import './App.css';

// ─── Config ───────────────────────────────────────────────────────────────────
const ALLOWED_DOMAIN = 'fastdolphin.com';
const BASE_URL = `${window.location.origin}${process.env.PUBLIC_URL}`;

// ─── Auth ─────────────────────────────────────────────────────────────────────
function isValidEmail(e) { return e.toLowerCase().endsWith(`@${ALLOWED_DOMAIN}`); }
function saveSession(e) { sessionStorage.setItem('fd_user', e); }
function getSession() { return sessionStorage.getItem('fd_user'); }
function clearSession() { sessionStorage.removeItem('fd_user'); }

// ─── Data fetchers ────────────────────────────────────────────────────────────
async function fetchIndex() {
  const res = await fetch(`${BASE_URL}/data/index.json?t=${Date.now()}`);
  if (!res.ok) throw new Error('No data available yet. Run the scraper first.');
  return res.json();
}

async function fetchLatest() {
  const res = await fetch(`${BASE_URL}/data/latest.json?t=${Date.now()}`);
  if (!res.ok) throw new Error('No data available yet. Run the scraper first.');
  return res.json();
}

async function fetchByDate(dateStr) {
  const res = await fetch(`${BASE_URL}/data/${dateStr}.json?t=${Date.now()}`);
  if (!res.ok) throw new Error(`No data for ${dateStr}`);
  return res.json();
}

async function fetchCountForDate(dateStr) {
  try {
    const res = await fetch(`${BASE_URL}/data/${dateStr}.json`);
    if (!res.ok) return null;
    const data = await res.json();
    return { count: data.count || 0, scraped_at: data.scraped_at_eastern || data.scraped_at || '', run_label: data.run_label || '' };
  } catch (_) { return null; }
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
  { key: 'Job Title',         label: 'Job Title',   sortable: true  },
  { key: 'Company',           label: 'Company',     sortable: true  },
  { key: 'Location',          label: 'Location',    sortable: true  },
  { key: 'Employment Type',   label: 'Emp. Type',   sortable: false },
  { key: 'Work Type',         label: 'Work',        sortable: false },
  { key: 'Corp to Corp',      label: 'C2C',         sortable: false },
  { key: 'Contract Duration', label: 'Duration',    sortable: false },
  { key: 'Pay',               label: 'Pay',         sortable: false },
  { key: 'Keyword',           label: 'Keyword',     sortable: true  },
  { key: 'AI Reason',         label: 'Why LATAM',   sortable: false },
  { key: 'Job URL',           label: '',            sortable: false },
];

function JobTable({ jobs }) {
  const [search, setSearch]   = useState('');
  const [sortCol, setSortCol] = useState('');
  const [sortDir, setSortDir] = useState('asc');
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
          <colgroup>
            <col style={{width:'180px'}} />
            <col style={{width:'140px'}} />
            <col style={{width:'130px'}} />
            <col style={{width:'320px'}} />
            <col style={{width:'90px'}}  />
            <col style={{width:'140px'}} />
            <col style={{width:'80px'}}  />
            <col style={{width:'110px'}} />
            <col style={{width:'90px'}}  />
            <col style={{width:'280px'}} />
            <col style={{width:'40px'}}  />
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
                  <td className="col-title">{job['Job Title']}</td>
                  <td className="col-company">{job['Company']}</td>
                  <td className="col-location">{job['Location']}</td>
                  <td><span className="tag tag-blue">{job['Employment Type'] || '—'}</span></td>
                  <td className="col-center">{job['Work Type'] || '—'}</td>
                  <td>{job['Corp to Corp'] || '—'}</td>
                  <td className="col-center">{job['Contract Duration'] || '—'}</td>
                  <td className="col-pay">{job['Pay'] || '—'}</td>
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

function formatDateStr(dateStr) {
  // Handle both "2026-07-08" and "2026-07-08-1430" formats
  const isModified = dateStr.length > 10;
  const datePart = dateStr.slice(0, 10);
  const timePart = isModified ? dateStr.slice(11) : '';
  const d = new Date(datePart + 'T12:00:00');
  const dateLabel = d.toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' });
  if (isModified) {
    const h = timePart.slice(0, 2), m = timePart.slice(2, 4);
    return `${dateLabel} · ${h}:${m} (Modified)`;
  }
  return dateLabel;
}

function HistoryCard({ dateStr, isActive, onClick }) {
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    fetchCountForDate(dateStr).then(setMeta);
  }, [dateStr]);

  const isModified = dateStr.length > 10;
  const datePart = dateStr.slice(0, 10);
  const d = new Date(datePart + 'T12:00:00');
  const dateLabel = d.toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' });

  const displayTime = meta?.scraped_at
    ? (() => {
        try {
          // Handle both ISO format with timezone and without
          const dateStr = meta.scraped_at.includes('+') || meta.scraped_at.endsWith('Z')
            ? meta.scraped_at
            : meta.scraped_at + 'Z'; // treat as UTC if no timezone
          const d = new Date(dateStr);
          if (isNaN(d.getTime())) return '';
          return d.toLocaleTimeString('en-US', {
            hour: 'numeric', minute: '2-digit',
            timeZone: 'America/New_York', timeZoneName: 'short'
          });
        } catch (_) { return ''; }
      })()
    : '';

  return (
    <button className={`history-card ${isActive ? 'active' : ''} ${isModified ? 'history-card-modified' : ''}`} onClick={onClick}>
      <Calendar size={20} className="history-icon" />
      <div className="history-card-body">
        <span className="history-date">{dateLabel}</span>
        {displayTime && <span className="history-time">{displayTime}{isModified ? ' · Modified' : ''}</span>}
        <span className="history-action">
          View {meta !== null ? `${meta.count} lead${meta.count !== 1 ? 's' : ''}` : '…'} →
        </span>
      </div>
    </button>
  );
}

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

// ─── Constants ────────────────────────────────────────────────────────────────
const GH_TOKEN = process.env.REACT_APP_GH_TOKEN;
const GH_OWNER = 'fastdolphin-cg';
const GH_REPO = 'dice-leads';
const GH_WORKFLOW = 'scraper.yml';

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

// ─── Run Scraper Tab ──────────────────────────────────────────────────────────
function RunScraperTab() {
  // Standard run state
  const [stdStatus, setStdStatus] = useState(null);
  const [stdMsg, setStdMsg]       = useState('');

  // Modified run state
  const [keywords, setKeywords]       = useState([...DEFAULT_KEYWORDS]);
  const [newKw, setNewKw]             = useState('');
  const [empTypes, setEmpTypes]       = useState(['CONTRACTS','THIRD_PARTY']);
  const [dateRange, setDateRange]     = useState(3);
  const [aiModel, setAiModel]         = useState('haiku');
  const [sendEmail, setSendEmail]     = useState(true);
  const [showSonnetWarn, setShowSonnetWarn] = useState(false);
  const [modStatus, setModStatus]     = useState(null);
  const [modMsg, setModMsg]           = useState('');

  async function runStandard() {
    setStdStatus('running');
    setStdMsg('');
    try {
      await triggerGitHubWorkflow({});
      setStdStatus('done');
      setStdMsg('Scraper started! Results will appear in ~15 minutes.');
    } catch (e) {
      setStdStatus('error');
      setStdMsg(e.message);
    }
  }

  async function runModified() {
    setModStatus('running');
    setModMsg('');
    try {
      const inputs = {
        keywords: keywords.join(','),
        employment_types: empTypes.join('|'),
        date_range: String(dateRange),
        ai_model: aiModel,
        send_email: String(sendEmail),
        run_label: 'Modified Run',
      };
      await triggerGitHubWorkflow(inputs);
      setModStatus('done');
      setModMsg('Modified scrape started! Results will appear in ~15 minutes.');
    } catch (e) {
      setModStatus('error');
      setModMsg(e.message);
    }
  }

  function toggleKw(kw) {
    setKeywords(prev => prev.includes(kw) ? prev.filter(k => k !== kw) : [...prev, kw]);
  }

  function addKw() {
    const k = newKw.trim().toLowerCase();
    if (k && !keywords.includes(k)) { setKeywords(prev => [...prev, k]); }
    setNewKw('');
  }

  function toggleEmp(id) {
    setEmpTypes(prev => prev.includes(id) ? prev.filter(e => e !== id) : [...prev, id]);
  }

  function handleModelChange(m) {
    if (m === 'sonnet') { setShowSonnetWarn(true); }
    else { setAiModel('haiku'); }
  }

  return (
    <div className="tab-content">
      <div className="tab-hero">
        <div className="tab-hero-text">
          <div className="tab-eyebrow">Manual trigger</div>
          <h2 className="tab-title">Run Scraper</h2>
          <p className="tab-sub">Runs automatically every day at 8AM Eastern. Use the buttons below to trigger a manual run.</p>
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
                <div className="run-schedule-value">Every day at 8:00 AM Eastern</div>
              </div>
            </div>
            <div className="run-details">
              <div className="run-detail-item"><span>Keywords</span><span>16 LATAM keywords</span></div>
              <div className="run-detail-item"><span>Employment type</span><span>Contract & Third Party</span></div>
              <div className="run-detail-item"><span>Date range</span><span>Last 3 days</span></div>
              <div className="run-detail-item"><span>AI model</span><span>Claude Haiku</span></div>
              <div className="run-detail-item"><span>Notification</span><span>Email on completion</span></div>
            </div>
          </div>
          <div className="run-action">
            <button className={`run-btn ${stdStatus === 'running' ? 'running' : ''}`}
              onClick={runStandard} disabled={stdStatus === 'running' || modStatus === 'running'}>
              {stdStatus === 'running'
                ? <><Loader2 size={16} className="spin" /> Starting…</>
                : <><Play size={16} /> Run Now</>}
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

            {/* Keywords */}
            <div className="mod-section">
              <div className="mod-label">Keywords</div>
              <div className="kw-chips">
                {DEFAULT_KEYWORDS.map(kw => (
                  <button key={kw} className={`kw-chip ${keywords.includes(kw) ? 'active' : 'inactive'}`}
                    onClick={() => toggleKw(kw)}>
                    {kw} {keywords.includes(kw) ? '×' : '+'}
                  </button>
                ))}
                {keywords.filter(k => !DEFAULT_KEYWORDS.includes(k)).map(kw => (
                  <button key={kw} className="kw-chip active custom"
                    onClick={() => toggleKw(kw)}>
                    {kw} ×
                  </button>
                ))}
              </div>
              <div className="kw-add">
                <input className="kw-input" placeholder="Add keyword…" value={newKw}
                  onChange={e => setNewKw(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addKw()} />
                <button className="kw-add-btn" onClick={addKw}>Add</button>
              </div>
            </div>

            {/* Employment Type */}
            <div className="mod-section">
              <div className="mod-label">Employment Type</div>
              <div className="check-group">
                {EMPLOYMENT_OPTIONS.map(opt => (
                  <label key={opt.id} className="check-item">
                    <input type="checkbox" checked={empTypes.includes(opt.id)}
                      onChange={() => toggleEmp(opt.id)} />
                    <span>{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Date Range */}
            <div className="mod-section">
              <div className="mod-label">Date Range — Last <strong>{dateRange}</strong> day{dateRange !== 1 ? 's' : ''}</div>
              <input type="range" min="1" max="30" value={dateRange}
                onChange={e => setDateRange(Number(e.target.value))}
                className="date-slider" />
              <div className="date-slider-labels"><span>1 day</span><span>30 days</span></div>
            </div>

            {/* AI Model */}
            <div className="mod-section">
              <div className="mod-label">AI Model</div>
              <div className="radio-group">
                <label className="radio-item">
                  <input type="radio" name="model" value="haiku" checked={aiModel === 'haiku'}
                    onChange={() => handleModelChange('haiku')} />
                  <span>Claude Haiku <em>(fast, ~$0.001/job)</em></span>
                </label>
                <label className="radio-item">
                  <input type="radio" name="model" value="sonnet" checked={aiModel === 'sonnet'}
                    onChange={() => handleModelChange('sonnet')} />
                  <span>Claude Sonnet 4.6 <em>(smarter, ~$0.01/job)</em></span>
                </label>
              </div>
            </div>

            {/* Notification */}
            <div className="mod-section">
              <div className="mod-label">Notification</div>
              <div className="radio-group">
                <label className="radio-item">
                  <input type="radio" name="notify" checked={sendEmail}
                    onChange={() => setSendEmail(true)} />
                  <span>Email on completion</span>
                </label>
                <label className="radio-item">
                  <input type="radio" name="notify" checked={!sendEmail}
                    onChange={() => setSendEmail(false)} />
                  <span>No email — results in app only</span>
                </label>
              </div>
            </div>

          </div>
          <div className="run-action">
            <button className={`run-btn run-btn-modified ${modStatus === 'running' ? 'running' : ''}`}
              onClick={runModified} disabled={modStatus === 'running' || stdStatus === 'running' || keywords.length === 0 || empTypes.length === 0}>
              {modStatus === 'running'
                ? <><Loader2 size={16} className="spin" /> Starting…</>
                : <><Play size={16} /> Run Modified Scrape</>}
            </button>
            {modStatus === 'done' && <div className="run-status done"><CheckCircle2 size={14} /> {modMsg}</div>}
            {modStatus === 'error' && <div className="run-status error"><AlertCircle size={14} /> {modMsg}</div>}
          </div>
        </div>

      </div>

      {/* Sonnet Warning Modal */}
      {showSonnetWarn && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-title">⚠️ Higher Cost Warning</div>
            <p className="modal-body">Claude Sonnet 4.6 is approximately <strong>10× more expensive</strong> than Haiku (~$0.01 per job vs ~$0.001). For a typical run of 20-30 jobs this could cost $0.20-$0.30 instead of $0.02-$0.03.</p>
            <p className="modal-body">Are you sure you want to use Sonnet for this run?</p>
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
  const [user, setUser]               = useState(getSession());
  const [activeTab, setActiveTab]     = useState('latest');
  const [dateIndex, setDateIndex]     = useState([]);
  const [jobs, setJobs]               = useState([]);
  const [currentDate, setCurrentDate] = useState('');
  const [scrapedAt, setScrapedAt]     = useState('');
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');
  const [runStatus, setRunStatus]     = useState(null);
  const [runMsg, setRunMsg]           = useState('');

  useEffect(() => {
    if (!user) return;
    loadLatest();
    loadIndex();
  }, [user]);

  async function loadLatest() {
    setLoading(true);
    setError('');
    try {
      const data = await fetchLatest();
      setJobs(data.jobs || []);
      setCurrentDate(data.tab || 'Latest');
      setScrapedAt(data.scraped_at || '');
    } catch (e) {
      setError(e.message);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }

  async function loadIndex() {
    try {
      const index = await fetchIndex();
      setDateIndex(index);
    } catch (_) {}
  }

  async function loadByDate(dateStr) {
    setLoading(true);
    setError('');
    setActiveTab('latest');
    try {
      const data = await fetchByDate(dateStr);
      setJobs(data.jobs || []);
      setCurrentDate(data.tab || dateStr);
      setScrapedAt(data.scraped_at || '');
    } catch (e) {
      setError(e.message);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }

  function triggerScraper() {
    setRunStatus('running');
    setTimeout(() => {
      window.open('https://github.com/fastdolphin-cg/dice-leads/actions/workflows/scraper.yml', '_blank');
      setRunStatus('done');
      setRunMsg('GitHub Actions opened in a new tab. Click "Run workflow" → "Run workflow" to start. Results will appear here after ~15 minutes.');
    }, 400);
  }

  const formattedScrapedAt = scrapedAt
    ? new Date(scrapedAt).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    : '';

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

      {/* Latest Leads */}
      {activeTab === 'latest' && (
        <div className="tab-content">
          <div className="tab-hero">
            <div className="tab-hero-text">
              <div className="tab-eyebrow">Dice.com · Last 3 days · Contract & Third Party · AI Verified</div>
              <h2 className="tab-title">LATAM Lead Finder</h2>
              <p className="tab-sub">
                {currentDate ? `Results from ${currentDate}` : 'Loading…'}
                {formattedScrapedAt && <span className="last-run"> · Scraped {formattedScrapedAt}</span>}
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

      {/* History */}
      {activeTab === 'history' && (
        <div className="tab-content">
          <div className="tab-hero">
            <div className="tab-hero-text">
              <div className="tab-eyebrow">Up to 7 most recent runs</div>
              <h2 className="tab-title">Run History</h2>
              <p className="tab-sub">Select any date to view that day's verified leads.</p>
            </div>
          </div>
          <div className="history-grid">
            {dateIndex.length === 0 ? (
              <div className="empty-state">
                <p className="empty-title">No history yet</p>
                <p className="empty-desc">Run the scraper to start building history.</p>
              </div>
            ) : (
              dateIndex.map(dateStr => (
                <HistoryCard key={dateStr} dateStr={dateStr} isActive={currentDate === dateStr}
                  onClick={() => loadByDate(dateStr)} />
              ))
            )}
          </div>
        </div>
      )}

      {/* Run Scraper */}
      {activeTab === 'run' && (
        <RunScraperTab />
      )}

      {/* AI Prompt */}
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
- Email signature or footer listing office locations such as "USA | CANADA | Mexico | INDIA" or "offices in New York, Mexico, India"
- Company boilerplate like "we have offices in..." or "presence in..." or "locations in..." or "internationally in..."
- Equal opportunity employment statements
- The US state of New Mexico - not the country Mexico
- The word "Perl" which is a programming language - this is NOT "Peru"
- A recruiter contact information or company address
- Phrases describing where the COMPANY operates, NOT where the CANDIDATE works

ACCEPT - answer YES - ONLY if Latin America, Spanish, Portuguese, or any related keyword appears in:
- The actual job requirements such as "must be bilingual" or "Spanish required" or "based in Mexico City"
- The candidate work location such as "position located in Bogota" or "remote from LATAM"
- Required skills or experience such as "LATAM market experience" or "serve Latin American clients"
- Language requirements such as "fluent Spanish" or "Portuguese required" or "bilingual English/Spanish"
- The role description itself mentioning LATAM work or clients
- Any Latin American country even if not in the keyword list above, as long as it is in the context of the job requirement and not just a company office mention

CONCRETE EXAMPLES:
- "USA | CANADA | Mexico | INDIA" in a footer = NO
- "Support Benefits implementation within the USA" with Mexico only in footer = NO
- "offices in Mexico City and India" = NO
- "PruTech has nearshore offices in Mexico City" but job is in Brooklyn NY = NO
- "Must be fluent in Spanish" = YES
- "Position based in Guadalajara" = YES
- "Serve LATAM clients" = YES
- "Bilingual English/Spanish required" = YES
- "Nearshore delivery from Mexico" = YES
- "Candidate must have experience working with teams in Paraguay" = YES

Job Title: {title}
Company: {company}
Location: {location}
Keyword that matched: {keyword}

Job Description:
{description}

Think step by step. Understand the nature of the job. Find every relevant mention. Determine its context. Then decide.

Respond with ONLY a JSON object in this exact format with no other text:
{"decision": "YES" or "NO", "reason": "one sentence explaining the specific mention and why it does or does not qualify"}`}
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
