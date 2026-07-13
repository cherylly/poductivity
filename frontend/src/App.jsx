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

function Layout({ children }) {
  return (
    <div className="app">
      <nav className="navbar">
        <div className="nav-brand">Content Digest</div>
        <div className="nav-links">
          <NavLink to="/" end>Digest</NavLink>
          <NavLink to="/bookmarks">Bookmarks</NavLink>
          <NavLink to="/sources">Sources</NavLink>
        </div>
      </nav>
      <main className="main-content">{children}</main>
    </div>
  )
}

function DigestList() {
  const { data: entries, loading } = useFetch(`${API}/entries?limit=50`)

  if (loading) return <div className="loading">Loading...</div>

  const grouped = {}
  ;(entries || []).forEach(e => {
    const date = e.published_at ? e.published_at.split('T')[0] : 'Unknown'
    if (!grouped[date]) grouped[date] = []
    grouped[date].push(e)
  })

  const dates = Object.keys(grouped).sort().reverse()

  return (
    <div className="digest-list">
      <h1>Your Content Digest</h1>
      <p className="subtitle">{entries?.length || 0} items across {dates.length} days</p>
      {dates.map(date => (
        <div key={date} className="date-group">
          <h2 className="date-header">{formatDate(date)}</h2>
          <div className="cards">
            {grouped[date].map(entry => (
              <EntryCard key={entry.id} entry={entry} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function EntryCard({ entry }) {
  const navigate = useNavigate()
  const typeIcons = { article: '📝', video: '🎬', podcast: '🎙️' }
  const typeColors = { article: '#e3f2fd', video: '#fce4ec', podcast: '#e8f5e9' }

  return (
    <div className="card" onClick={() => navigate(`/entry/${entry.id}`)}>
      <div className="card-top">
        <span className="badge" style={{ background: typeColors[entry.content_type] }}>
          {typeIcons[entry.content_type]} {entry.content_type}
        </span>
        <span className="source-name">{entry.source_name}</span>
        {entry.bookmarked && <span className="bookmark-icon">★</span>}
      </div>
      <h3 className="card-title">{entry.title}</h3>
      {entry.summary && (
        <>
          <p className="card-thesis">{entry.summary.thesis}</p>
          <div className="card-tags">
            {entry.summary.tags?.slice(0, 3).map(tag => (
              <span key={tag} className="tag">{tag}</span>
            ))}
          </div>
        </>
      )}
      {!entry.summary && <p className="card-status">Status: {entry.status}</p>}
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

  if (loading) return <div className="loading">Loading...</div>
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
          <span className="badge" style={{ background: entry.content_type === 'article' ? '#e3f2fd' : entry.content_type === 'video' ? '#fce4ec' : '#e8f5e9' }}>
            {entry.content_type}
          </span>
          <span className="source-name">{entry.source_name}</span>
          {entry.published_at && <span className="date">{formatDate(entry.published_at.split('T')[0])}</span>}
        </div>
        <h1>{entry.title}</h1>
        <div className="detail-actions">
          <a href={entry.url} target="_blank" rel="noopener noreferrer" className="btn btn-primary">
            View Original
          </a>
          <button onClick={toggleBookmark} className={`btn btn-bookmark ${bookmarked ? 'active' : ''}`}>
            {bookmarked ? '★ Bookmarked' : '☆ Bookmark'}
          </button>
        </div>
      </div>

      {entry.summary && (
        <div className="summary-content">
          <section className="thesis-section">
            <h2>Core Thesis</h2>
            <p className="thesis">{entry.summary.thesis}</p>
          </section>

          <section className="keypoints-section">
            <h2>Key Points</h2>
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
            <h2>Conclusion</h2>
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

  if (loading) return <div className="loading">Loading...</div>

  return (
    <div className="digest-list">
      <h1>Bookmarks</h1>
      <p className="subtitle">{entries?.length || 0} saved items</p>
      {entries?.length === 0 && (
        <p className="empty-state">No bookmarks yet. Click the star on any entry to save it.</p>
      )}
      <div className="cards">
        {(entries || []).map(entry => (
          <EntryCard key={entry.id} entry={entry} />
        ))}
      </div>
    </div>
  )
}

function Sources() {
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
    if (!confirm('Remove this source?')) return
    await fetch(`${API}/sources/${id}`, { method: 'DELETE' })
    loadSources()
  }

  if (loading) return <div className="loading">Loading...</div>

  return (
    <div className="sources-page">
      <div className="page-header">
        <h1>Subscription Sources</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ Add Source'}
        </button>
      </div>

      {showForm && (
        <form className="source-form" onSubmit={addSource}>
          <input
            placeholder="Name (e.g. Lenny's Newsletter)"
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
            placeholder="URL (RSS feed or channel URL)"
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
            <div className="source-info">
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
  if (url.includes('youtube.com') || url.includes('youtu.be')) {
    const parts = timestamp.split(':')
    const seconds = parts.length === 2
      ? parseInt(parts[0]) * 60 + parseInt(parts[1])
      : parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2])
    return `${url}&t=${seconds}`
  }
  return url
}

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
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
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
