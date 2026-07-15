import { useState, useEffect } from 'react'
import './News.css'

const API = '/api'

function News() {
  const [news, setNews] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const today = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })

  const fetchNews = async () => {
    try {
      const res = await fetch(`${API}/news`)
      if (res.ok) {
        const data = await res.json()
        setNews(data)
      }
    } catch (e) {
      console.error('Failed to fetch news:', e)
    } finally {
      setLoading(false)
    }
  }

  const refreshNews = async () => {
    setRefreshing(true)
    try {
      const res = await fetch(`${API}/news/fetch`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setNews(data)
      }
    } catch (e) {
      console.error('Failed to refresh news:', e)
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchNews()
  }, [])

  return (
    <div className="news-page">
      <div className="page-header">
        <h1>&#128663; 智驾行业新闻</h1>
        <p className="subtitle">{today} · 每日推送</p>
      </div>

      <div className="action-bar">
        <button
          className="btn btn-primary"
          onClick={refreshNews}
          disabled={refreshing}
        >
          {refreshing ? '正在获取...' : '获取最新新闻'}
        </button>
      </div>

      {loading ? (
        <div className="loading">加载中...</div>
      ) : news.length === 0 ? (
        <div className="empty-state">
          <p>暂无新闻数据</p>
          <p>点击"获取最新新闻"按钮获取今日行业热点</p>
        </div>
      ) : (
        <div className="news-list">
          {news.map((item, idx) => (
            <div key={idx} className="news-item">
              <div className="news-meta">
                <span className="news-source">{item.source}</span>
                <span className="news-date">{item.published_at}</span>
              </div>
              <h3 className="news-title">
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noopener noreferrer">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </h3>
              {item.summary && (
                <p className="news-summary">{item.summary}</p>
              )}
              {item.tags && item.tags.length > 0 && (
                <div className="news-tags">
                  {item.tags.map(tag => (
                    <span key={tag} className="news-tag">{tag}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default News