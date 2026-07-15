import { NavLink } from 'react-router-dom'
import './Home.css'

function Home() {
  const today = new Date()
  const dateStr = today.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long'
  })

  return (
    <div className="home-page">
      <div className="hero-section">
        <h1 className="hero-title">Welcome to My Personal Hub</h1>
        <p className="hero-subtitle">{dateStr}</p>
        <p className="hero-desc">知识管理 · 行业洞察 · 成长记录</p>
      </div>

      <div className="feature-grid">
        <NavLink to="/digest" className="feature-card">
          <div className="feature-icon">&#128240;</div>
          <h2 className="feature-title">内容摘要</h2>
          <p className="feature-desc">每日订阅内容聚合与 AI 摘要，涵盖 Substack、YouTube、Podcast</p>
          <span className="feature-link">进入 &rarr;</span>
        </NavLink>

        <NavLink to="/news" className="feature-card">
          <div className="feature-icon">&#128663;</div>
          <h2 className="feature-title">行业新闻</h2>
          <p className="feature-desc">智驾行业每日热点新闻推送，跟踪最新动态</p>
          <span className="feature-link">进入 &rarr;</span>
        </NavLink>

        <NavLink to="/thinking" className="feature-card">
          <div className="feature-icon">&#129504;</div>
          <h2 className="feature-title">每日思考</h2>
          <p className="feature-desc">每日 3 个出海行业面试问题，助力面试准备</p>
          <span className="feature-link">进入 &rarr;</span>
        </NavLink>
      </div>

      <div className="quote-section">
        <p className="quote-text">"The best way to predict the future is to create it."</p>
        <p className="quote-author">- Peter Drucker</p>
      </div>
    </div>
  )
}

export default Home