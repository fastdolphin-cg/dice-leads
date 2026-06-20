import React, { useState, useEffect, useMemo } from 'react';
import { Search, LogOut, Download, RefreshCw, ChevronUp, ChevronDown, ExternalLink, Filter, X, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import './App.css';

// ─── Config ───────────────────────────────────────────────────────────────────
const ALLOWED_DOMAIN = 'fastdolphin.com';

const KEYWORDS = [
  'mexico', 'spanish', 'brazil', 'argentina', 'colombia',
  'ecuador', 'costa rica', 'panama', 'portuguese', 'latam',
  'latin america', 'Brasil', 'maquiladora', 'chile', 'bolivia', 'peru'
];

// Phrases that indicate a location is just an office mention, not the job location
const OFFICE_MENTION_PATTERNS = [
  /offices?\s+in\s+[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latin america|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /locations?\s+in\s+[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latin america|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /offices?\s+including[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latin america|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /internationally\s+in\s+[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latin america|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /presence\s+in\s+[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latin america|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /headquartered[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latin america|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /new mexico/i,
];

// These indicate the job IS actually in LATAM
const LATAM_JOB_PATTERNS = [
  /location\s*:\s*[^.\n]*(mexico|brazil|brasil|colombia|argentina|chile|latam|latin america|bolivia|peru|costa rica|panama|ecuador)/i,
  /position\s+is\s+in\s+[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /role\s+is\s+in\s+[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /based\s+in\s+[^.]*?(mexico|brazil|brasil|colombia|argentina|chile|latam|bolivia|peru|costa rica|panama|ecuador)/i,
  /\b(guadalajara|monterrey|mexico city|ciudad de mexico|cdmx|bogota|medellin|buenos aires|santiago|lima|san jose|panama city|quito|la paz|sao paulo|rio de janeiro|brasilia)\b/i,
  /spanish[\s-]speaking/i,
  /bilingual.*spanish/i,
  /fluent.*spanish/i,
  /spanish.*required/i,
  /portuguese[\s-]speaking/i,
  /latam\s+(region|market|team|operations)/i,
  /latin\s+america\s+(region|market|team|operations|experience)/i,
];

function isRealLatamJob(title, description, location) {
  const fullText = `${title} ${description} ${location}`.toLowerCase();

  // Immediately reject "New Mexico" unless paired with real LATAM signals
  if (/new\s+mexico/i.test(fullText) && !/\b(mexico city|guadalajara|monterrey|cdmx|maquiladora)\b/i.test(fullText)) {
    return false;
  }

  // Check if any LATAM job pattern matches (strong positive signal)
  for (const pattern of LATAM_JOB_PATTERNS) {
    if (pattern.test(fullText)) return true;
  }

  // Check if keyword mention is just an office mention (negative signal)
  for (const pattern of OFFICE_MENTION_PATTERNS) {
    if (pattern.test(fullText)) return false;
  }

  // Default: if it has a LATAM keyword in title or location, keep it
  const titleLoc = `${title} ${location}`.toLowerCase();
  const latamWords = ['mexico', 'brazil', 'brasil', 'colombia', 'argentina', 'chile', 'latam', 'latin america', 'bolivia', 'peru', 'costa rica', 'panama', 'ecuador', 'maquiladora'];
  return latamWords.some(w => titleLoc.includes(w));
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
function isValidEmail(e) { return e.toLowerCase().endsWith(`@${ALLOWED_DOMAIN}`); }
function saveSession(e) { sessionStorage.setItem('fd_user', e); }
function getSession() { return sessionStorage.getItem('fd_user'); }
function clearSession() { sessionStorage.removeItem('fd_user'); }

// ─── Scraping ─────────────────────────────────────────────────────────────────
async function fetchHtml(url) {
  const proxies = [
    `https://corsproxy.io/?${encodeURIComponent(url)}`,
    `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
    `https://thingproxy.freeboard.io/fetch/${url}`,
  ];
  for (const proxy of proxies) {
    try {
      const res = await fetch(proxy, { headers: { 'x-requested-with': 'XMLHttpRequest' } });
      if (res.ok) {
        const text = await res.text();
        if (text && text.length > 500) return text;
      }
    } catch (_) { continue; }
  }
  throw new Error('All proxies failed');
}

function parseJobsFromHtml(html, keyword) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const jobs = [];

  // Try __NEXT_DATA__ JSON first
  const nextDataScript = doc.querySelector('#__NEXT_DATA__');
  if (nextDataScript) {
    try {
      const nextData = JSON.parse(nextDataScript.textContent);
      const props = nextData?.props?.pageProps;
      const jobList =
        props?.initialState?.jobs?.jobs ||
        props?.jobs ||
        props?.searchResults?.jobs ||
        [];

      if (jobList.length > 0) {
        for (const job of jobList) {
          const empType = Array.isArray(job.employmentType)
            ? job.employmentType.join(', ')
            : (job.employmentType || '');

          const loc = job.jobLocation || job.location || {};
          const location = typeof loc === 'string' ? loc
            : [loc.city, loc.state, loc.country].filter(Boolean).join(', ');

          const description = job.jobDescription
            ? job.jobDescription.replace(/<[^>]+>/g, ' ').slice(0, 1000)
            : '';

          if (!isRealLatamJob(job.title || '', description, location)) continue;

          jobs.push({
            id: job.id || Math.random().toString(36).slice(2),
            title: job.title || '',
            company: job.hiringOrganization?.name || job.advertiserName || '',
            location,
            employmentType: empType,
            workType: job.workFromHomeAvailability || '',
            pay: job.salary || '',
            postedDate: job.datePosted || job.date || '',
            url: `https://www.dice.com/job-detail/${job.id}`,
            keyword,
          });
        }
        return jobs;
      }
    } catch (_) {}
  }

  // Fallback: parse HTML cards
  const cards = doc.querySelectorAll('div[data-cy="search-result-item"], div[role="listitem"], [data-testid="job-card"]');
  for (const card of cards) {
    const titleEl = card.querySelector('a[data-testid="job-search-job-detail-link"], h5 a, .job-title a');
    const companyEl = card.querySelector('p.mb-0, [data-cy="company-name"]');
    const locEl = card.querySelector('[data-cy="location"], li[data-cy="location"]');
    const linkEl = card.querySelector('a[data-testid="job-search-job-card-link"], a[href*="job-detail"]');
    const empTypeEl = card.querySelector('[data-cy="employment-type"], [data-testid="employment-type"]');
    const workTypeEl = card.querySelector('[data-cy="work-type"], [data-testid="work-type"]');
    const payEl = card.querySelector('[data-cy="pay"], [data-testid="pay"]');
    const dateEl = card.querySelector('[data-cy="posted-date"], time, [data-testid="posted-date"]');

    const title = titleEl?.textContent?.trim() || '';
    const company = companyEl?.textContent?.trim() || '';
    const location = locEl?.textContent?.trim() || '';
    const href = linkEl?.getAttribute('href') || '';
    const url = href.startsWith('http') ? href : `https://www.dice.com${href}`;

    if (!title) continue;
    if (!isRealLatamJob(title, '', location)) continue;

    jobs.push({
      id: url.split('/').pop() || Math.random().toString(36).slice(2),
      title, company, location,
      employmentType: empTypeEl?.textContent?.trim() || '',
      workType: workTypeEl?.textContent?.trim() || '',
      pay: payEl?.textContent?.trim() || '',
      postedDate: dateEl?.getAttribute('datetime') || dateEl?.textContent?.trim() || '',
      url, keyword,
    });
  }
  return jobs;
}

async function scrapeKeyword(keyword, page, onProgress) {
  const url = `https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=${encodeURIComponent(keyword)}&page=${page}`;
  onProgress(`Searching "${keyword}" (page ${page})…`);
  const html = await fetchHtml(url);
  return parseJobsFromHtml(html, keyword);
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
        <div className="login-logo">
          <FDLogo className="login-fd-logo" />
        </div>
        <h1 className="login-title">Lead Finder</h1>
        <p className="login-sub">Sign in with your Fast Dolphin email to access LATAM contract leads from Dice.</p>
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

// ─── Fast Dolphin Logo ────────────────────────────────────────────────────────
function FDLogo({ className = '', height = 36 }) {
  return (
    <img
      src={`${process.env.PUBLIC_URL}/fd-logo.png`}
      alt="Fast Dolphin"
      height={height}
      className={className}
      style={{ objectFit: 'contain' }}
    />
  );
}

// ─── Status Bar ───────────────────────────────────────────────────────────────
function StatusBar({ status, progress }) {
  if (!status) return null;
  return (
    <div className={`status-bar ${status}`}>
      {status === 'running' && <Loader2 size={14} className="spin" />}
      {status === 'done' && <CheckCircle2 size={14} />}
      {status === 'error' && <AlertCircle size={14} />}
      <span className="status-text">{progress}</span>
    </div>
  );
}

// ─── Table ────────────────────────────────────────────────────────────────────
const COLUMNS = [
  { key: 'title',          label: 'Job Title',       sortable: true  },
  { key: 'company',        label: 'Company',         sortable: true  },
  { key: 'location',       label: 'Location',        sortable: true  },
  { key: 'employmentType', label: 'Employment Type', sortable: false },
  { key: 'workType',       label: 'Work Type',       sortable: false },
  { key: 'pay',            label: 'Pay',             sortable: false },
  { key: 'postedDate',     label: 'Posted',          sortable: true  },
  { key: 'keyword',        label: 'Keyword',         sortable: true  },
  { key: 'url',            label: 'Link',            sortable: false },
];

function JobTable({ jobs }) {
  const [search, setSearch]     = useState('');
  const [sortCol, setSortCol]   = useState('postedDate');
  const [sortDir, setSortDir]   = useState('desc');
  const [filterKw, setFilterKw] = useState('');

  const keywords = useMemo(() => [...new Set(jobs.map(j => j.keyword))].sort(), [jobs]);

  const filtered = useMemo(() => {
    let rows = [...jobs];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(j =>
        j.title.toLowerCase().includes(q) ||
        j.company.toLowerCase().includes(q) ||
        j.location.toLowerCase().includes(q)
      );
    }
    if (filterKw) rows = rows.filter(j => j.keyword === filterKw);
    rows.sort((a, b) => {
      const av = a[sortCol] || '', bv = b[sortCol] || '';
      return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });
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
              : filtered.map(job => (
                <tr key={job.id} className="job-row">
                  <td className="col-title">{job.title}</td>
                  <td className="col-company">{job.company}</td>
                  <td className="col-location">{job.location}</td>
                  <td><span className="tag tag-blue">{job.employmentType || '—'}</span></td>
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
            }
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [user, setUser]           = useState(getSession());
  const [scrapeStatus, setStatus] = useState(null);
  const [progress, setProgress]   = useState('');
  const [jobs, setJobs]           = useState([]);
  const [lastRun, setLastRun]     = useState(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem('fd_jobs');
      const savedTime = localStorage.getItem('fd_last_run');
      if (saved) setJobs(JSON.parse(saved));
      if (savedTime) setLastRun(new Date(savedTime));
    } catch (_) {}
  }, []);

  async function runScrape() {
    setStatus('running');
    setJobs([]);
    const found = [];
    const seen = new Set();
    let errors = 0;

    for (let ki = 0; ki < KEYWORDS.length; ki++) {
      const kw = KEYWORDS[ki];
      for (let page = 1; page <= 3; page++) {
        try {
          setProgress(`Searching "${kw}" (${ki + 1}/${KEYWORDS.length})…`);
          const results = await scrapeKeyword(kw, page, setProgress);
          if (!results.length) break;
          let newOnPage = 0;
          for (const job of results) {
            if (seen.has(job.id)) continue;
            seen.add(job.id);
            found.push(job);
            newOnPage++;
          }
          if (newOnPage === 0) break;
        } catch (err) {
          console.warn(`Error on "${kw}" page ${page}:`, err.message);
          errors++;
          break;
        }
        await new Promise(r => setTimeout(r, 600));
      }
    }

    const now = new Date();
    setJobs(found);
    setLastRun(now);
    localStorage.setItem('fd_jobs', JSON.stringify(found));
    localStorage.setItem('fd_last_run', now.toISOString());

    if (found.length > 0) {
      setStatus('done');
      setProgress(`Found ${found.length} verified LATAM leads across ${KEYWORDS.length} keywords.`);
    } else {
      setStatus('error');
      setProgress(`No results returned. Dice may be blocking the proxy. Try again in a few minutes.`);
    }
  }

  if (!user) return <LoginScreen onLogin={email => setUser(email)} />;

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-inner">
          <FDLogo height={38} />
          <div className="header-right">
            <span className="header-user">{user}</span>
            <button className="logout-btn" onClick={() => { clearSession(); setUser(null); }} title="Sign out">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-text">
            <div className="hero-eyebrow">Dice.com · Last 3 days · Contract & Third Party</div>
            <h2 className="hero-title">LATAM Lead Finder</h2>
            <p className="hero-sub">
              Verified contract opportunities matching Latin America keywords.
              {lastRun && <span className="last-run"> Last pull: {lastRun.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>}
            </p>
          </div>
          <button className={`scrape-btn ${scrapeStatus === 'running' ? 'running' : ''}`}
            onClick={runScrape} disabled={scrapeStatus === 'running'}>
            {scrapeStatus === 'running'
              ? <><Loader2 size={16} className="spin" /> Pulling leads…</>
              : <><RefreshCw size={16} /> Pull fresh leads</>}
          </button>
        </div>
        <StatusBar status={scrapeStatus} progress={progress} />
      </section>

      {/* Stats */}
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
        {jobs.length > 0 ? <JobTable jobs={jobs} /> : (
          <div className="empty-state">
            <FDLogo height={48} className="empty-logo" />
            <p className="empty-title">No leads yet</p>
            <p className="empty-desc">Click "Pull fresh leads" to search Dice for verified LATAM contract opportunities.</p>
          </div>
        )}
      </main>

      <footer className="app-footer">Fast Dolphin Consulting Group · Internal use only · {new Date().getFullYear()}</footer>
    </div>
  );
}
