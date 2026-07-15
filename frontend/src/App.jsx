import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useParams, useNavigate } from 'react-router-dom'
import './App.css'

const API = '/api'

function useFetch(url) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    fetch(url)
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e); setLoading(false) })
  }, [url])

  return { data, loading, error }
}

function useTheme() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('theme')
    return saved === 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return [dark, () => setDark(d => !d)]
}

function Layout({ children }) {
  const [dark, toggleTheme] = useTheme()
  const today = new Date()
  const edition = today.toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  })

  return (
    <div className="app">
      <nav className="navbar">
        <button className="theme-toggle" onClick={toggleTheme} title={dark ? 'Light mode' : 'Dark mode'}>
          {dark ? '\u2600' : '\u263E'}
        </button>
        <div className="nav-brand">The Daily Digest</div>
        <div className="nav-edition">{edition} &mdash; Your Personal Edition</div>
        <div className="nav-links">
          <NavLink to="/" end>Front Page</NavLink>
          <NavLink to="/bookmarks">Clippings</NavLink>
          <NavLink to="/sources">Subscriptions</NavLink>
          <NavLink to="/archive">Past Issues</NavLink>
        </div>
      </nav>
      <main className="main-content">{children}</main>
    </div>
  )
}

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function DigestList() {
  const { data: entries, loading } = useFetch(`${API}/entries?limit=50&lite=true`)

  if (loading) return <div className="loading">Fetching today&rsquo;s edition&hellip;</div>

  const today = todayStr()
  const todayEntries = (entries || []).filter(e => {
    const fetchLocal = e.created_at ? toLocalDateStr(e.created_at) : ''
    const pubLocal = e.published_at ? toLocalDateStr(e.published_at) : ''
    return fetchLocal === today || pubLocal === today
  })

  return (
    <div className="digest-list">
      <h1>Today&rsquo;s Edition</h1>
      <p className="subtitle">{formatDateNewspaper(today)} &mdash; {todayEntries.length} stories</p>
      {todayEntries.length === 0 ? (
        <p className="empty-state">No new stories today. Check back later or browse <NavLink to="/archive" style={{color: 'var(--accent)'}}>past issues</NavLink>.</p>
      ) : (
        <div className="cards">
          {todayEntries.map(entry => (
            <EntryCard key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}

function Archive() {
  const { data: entries, loading } = useFetch(`${API}/entries?limit=500&lite=true`)
  const navigate = useNavigate()

  if (loading) return <div className="loading">Loading archive&hellip;</div>

  const today = todayStr()
  const grouped = {}
  ;(entries || []).forEach(e => {
    const fetchLocal = e.created_at ? toLocalDateStr(e.created_at) : ''
    const pubLocal = e.published_at ? toLocalDateStr(e.published_at) : 'Unknown'
    if (fetchLocal === today || pubLocal === today) return
    const groupDate = pubLocal || fetchLocal
    if (!grouped[groupDate]) grouped[groupDate] = []
    grouped[groupDate].push(e)
  })

  const dates = Object.keys(grouped).sort().reverse()

  return (
    <div className="digest-list">
      <h1>Past Issues</h1>
      <p className="subtitle">{dates.length} editions in the archive</p>
      <div className="archive-list">
        {dates.map(date => (
          <div
            key={date}
            className="archive-item"
            onClick={() => navigate(`/archive/${date}`)}
          >
            <span className="archive-date">{formatDateNewspaper(date)}</span>
            <span className="archive-count">{grouped[date].length} stories</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ArchiveDay() {
  const { date } = useParams()
  const { data: entries, loading } = useFetch(`${API}/entries?limit=500&lite=true`)

  if (loading) return <div className="loading">Loading&hellip;</div>

  const dayEntries = (entries || []).filter(e => {
    const pubDate = e.published_at ? e.published_at.split('T')[0] : ''
    return pubDate === date
  })

  return (
    <div className="digest-list">
      <h1>{formatDateNewspaper(date)}</h1>
      <p className="subtitle">{dayEntries.length} stories &mdash; <NavLink to="/archive" style={{color: 'var(--accent)'}}>Back to Archive</NavLink></p>
      <div className="cards">
        {dayEntries.map(entry => (
          <EntryCard key={entry.id} entry={entry} />
        ))}
      </div>
    </div>
  )
}

function EntryCard({ entry }) {
  const navigate = useNavigate()

  return (
    <div className="card" onClick={() => navigate(`/entry/${entry.id}`)}>
      <div className="card-top">
        <span className="badge">
          {entry.content_type === 'article' ? 'Substack' : entry.content_type === 'video' ? 'YouTube' : entry.content_type}
        </span>
        <span className="source-name">{entry.source_name}</span>
        {entry.transcript_source === 'description' && (
          <span className="transcript-badge desc">Description Only</span>
        )}
        {entry.transcript_source === 'transcript' && (
          <span className="transcript-badge full">Full Transcript</span>
        )}
        {entry.bookmarked && <span className="bookmark-icon">&starf;</span>}
      </div>
      <h3 className="card-title">{entry.title}</h3>
      {entry.summary && (
        <>
          <p className="card-thesis">{entry.summary.thesis}</p>
          <div className="card-tags">
            {entry.summary.tags?.slice(0, 4).map(tag => (
              <span key={tag} className="tag">{tag}</span>
            ))}
          </div>
        </>
      )}
      {!entry.summary && <p className="card-status">{entry.status}</p>}
    </div>
  )
}

function EntryDetail() {
  const { id } = useParams()
  const { data: entry, loading } = useFetch(`${API}/entries/${id}`)
  const [bookmarked, setBookmarked] = useState(false)

  useEffect(() => {
    if (entry) setBookmarked(entry.bookmarked)
  }, [entry])

  if (loading) return <div className="loading">Loading&hellip;</div>
  if (!entry) return <div className="error">Entry not found</div>

  const toggleBookmark = async () => {
    const method = bookmarked ? 'DELETE' : 'POST'
    await fetch(`${API}/bookmarks/${id}`, { method })
    setBookmarked(!bookmarked)
  }

  return (
    <div className="entry-detail">
      <div className="detail-header">
        <div className="detail-meta">
          <span className="badge">{entry.content_type === 'article' ? 'Substack' : entry.content_type === 'video' ? 'YouTube' : entry.content_type}</span>
          <span className="source-name">{entry.source_name}</span>
          {entry.published_at && <span className="date">{formatDateNewspaper(entry.published_at.split('T')[0])}</span>}
          {entry.transcript_source === 'description' && (
            <span className="transcript-badge desc">Based on Description</span>
          )}
          {entry.transcript_source === 'transcript' && (
            <span className="transcript-badge full">Based on Full Transcript</span>
          )}
        </div>
        <h1>{entry.title}</h1>
        <div className="detail-actions">
          {entry.url ? (
            <a href={entry.url} target="_blank" rel="noopener noreferrer" className="btn btn-primary">
              Read Original
            </a>
          ) : (
            <span className="btn" style={{ opacity: 0.4, cursor: 'default' }}>No Link Available</span>
          )}
          <button onClick={toggleBookmark} className={`btn btn-bookmark ${bookmarked ? 'active' : ''}`}>
            {bookmarked ? '\u2605 Clipped' : '\u2606 Clip'}
          </button>
        </div>
      </div>

      {entry.summary && (
        <div className="summary-content">
          <section className="thesis-section">
            <h2>Abstract</h2>
            <p className="thesis">{entry.summary.thesis}</p>
          </section>

          <section className="keypoints-section">
            <h2>Key Highlights</h2>
            <ul className="keypoints">
              {entry.summary.key_points.map((point, i) => (
                <li key={i} className="keypoint">
                  {point.topic && <strong className="point-topic">{point.topic}</strong>}
                  {point.speaker && <span className="speaker">{point.speaker}</span>}
                  <span className="point-text">{point.text}</span>
                  {point.timestamp && (
                    <a
                      href={getTimestampLink(entry.url, point.timestamp)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="timestamp"
                    >
                      {point.timestamp}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </section>

          {entry.summary.actionable_takeaways?.length > 0 && (
            <section className="takeaways-section">
              <h2>Actionable Takeaways</h2>
              <ul className="takeaways">
                {entry.summary.actionable_takeaways.map((t, i) => (
                  <li key={i} className="takeaway-item">{t}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="conclusion-section">
            <h2>Summary</h2>
            <p className="conclusion">{entry.summary.conclusion}</p>
          </section>

          {entry.summary.tags?.length > 0 && (
            <div className="tags-section">
              {entry.summary.tags.map(tag => (
                <span key={tag} className="tag">{tag}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Bookmarks() {
  const { data: entries, loading } = useFetch(`${API}/bookmarks`)

  if (loading) return <div className="loading">Loading clippings&hellip;</div>

  return (
    <div className="digest-list">
      <h1>Clippings</h1>
      <p className="subtitle">{entries?.length || 0} saved articles</p>
      {entries?.length === 0 && (
        <p className="empty-state">Your clippings folder is empty. Click the star on any story to save it here.</p>
      )}
      <div className="cards">
        {(entries || []).map(entry => (
          <EntryCard key={entry.id} entry={entry} />
        ))}
      </div>
    </div>
  )
}

function SourceEntries() {
  const { id } = useParams()
  const { data: entries, loading } = useFetch(`${API}/entries?limit=200&lite=true&source_id=${id}`)
  const { data: sources } = useFetch(`${API}/sources`)

  if (loading) return <div className="loading">Loading&hellip;</div>

  const source = (sources || []).find(s => s.id === parseInt(id))
  const sourceName = source ? source.name : 'Source'

  return (
    <div className="digest-list">
      <h1>{sourceName}</h1>
      <p className="subtitle">{(entries || []).length} articles &mdash; <NavLink to="/sources" style={{color: 'var(--accent)'}}>Back to Subscriptions</NavLink></p>
      <div className="cards">
        {(entries || []).map(entry => (
          <EntryCard key={entry.id} entry={entry} />
        ))}
      </div>
    </div>
  )
}

function Sources() {
  const navigate = useNavigate()
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', platform: 'substack', url: '' })

  const loadSources = () => {
    fetch(`${API}/sources`)
      .then(r => r.json())
      .then(d => { setSources(d); setLoading(false) })
  }

  useEffect(loadSources, [])

  const addSource = async (e) => {
    e.preventDefault()
    await fetch(`${API}/sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    setForm({ name: '', platform: 'substack', url: '' })
    setShowForm(false)
    loadSources()
  }

  const deleteSource = async (id) => {
    if (!confirm('Remove this subscription?')) return
    await fetch(`${API}/sources/${id}`, { method: 'DELETE' })
    loadSources()
  }

  if (loading) return <div className="loading">Loading subscriptions&hellip;</div>

  return (
    <div className="sources-page">
      <div className="page-header">
        <h1>Subscriptions</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ Subscribe'}
        </button>
      </div>

      {showForm && (
        <form className="source-form" onSubmit={addSource}>
          <input
            placeholder="Publication name"
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            required
          />
          <select value={form.platform} onChange={e => setForm({ ...form, platform: e.target.value })}>
            <option value="substack">Substack</option>
            <option value="youtube">YouTube</option>
            <option value="podcast">Podcast</option>
          </select>
          <input
            placeholder="RSS feed or channel URL"
            value={form.url}
            onChange={e => setForm({ ...form, url: e.target.value })}
            required
          />
          <button type="submit" className="btn btn-primary">Add</button>
        </form>
      )}

      <div className="sources-list">
        {sources.map(s => (
          <div key={s.id} className="source-item">
            <div className="source-info" onClick={() => navigate(`/source/${s.id}`)} style={{cursor: 'pointer'}}>
              <span className="platform-badge">{s.platform}</span>
              <span className="source-title">{s.name}</span>
              <span className={`status-dot ${s.active ? 'active' : 'inactive'}`} />
            </div>
            <div className="source-url">{s.url}</div>
            <button className="btn btn-danger btn-sm" onClick={() => deleteSource(s.id)}>Remove</button>
          </div>
        ))}
      </div>
    </div>
  )
}

function getTimestampLink(url, timestamp) {
  if (!url) return '#'
  if (url.includes('youtube.com') || url.includes('youtu.be')) {
    const parts = timestamp.split(':')
    const seconds = parts.length === 2
      ? parseInt(parts[0]) * 60 + parseInt(parts[1])
      : parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2])
    return `${url}&t=${seconds}`
  }
  return url
}

function toLocalDateStr(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z')
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatDateNewspaper(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
  })
}

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DigestList />} />
          <Route path="/entry/:id" element={<EntryDetail />} />
          <Route path="/bookmarks" element={<Bookmarks />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/source/:id" element={<SourceEntries />} />
          <Route path="/archive" element={<Archive />} />
          <Route path="/archive/:date" element={<ArchiveDay />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
