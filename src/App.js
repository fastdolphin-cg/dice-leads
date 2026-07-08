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
                <button key={dateStr} className={`history-card ${currentDate === dateStr ? 'active' : ''}`}
                  onClick={() => loadByDate(dateStr)}>
                  <Calendar size={20} className="history-icon" />
                  <span className="history-date">{new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' })}</span>
                  <span className="history-action">View leads →</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* Run Scraper */}
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
                  <div className="run-status done"><CheckCircle2 size={16} /> {runMsg}</div>
                )}
                {!runStatus && (
                  <p className="run-note">Clicking "Run Now" opens GitHub Actions in a new tab. Click "Run workflow" to start the scraper. Results appear here after ~15 minutes.</p>
                )}
              </div>
            </div>
          </div>
        </div>
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
