import { useState, useEffect } from 'react'
import './Thinking.css'

const API = '/api'

function Thinking() {
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [answers, setAnswers] = useState({})
  const [showAnswers, setShowAnswers] = useState({})

  const today = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })

  const fetchQuestions = async () => {
    try {
      const res = await fetch(`${API}/thinking/questions`)
      if (res.ok) {
        const data = await res.json()
        setQuestions(data)
      }
    } catch (e) {
      console.error('Failed to fetch questions:', e)
    } finally {
      setLoading(false)
    }
  }

  const generateQuestions = async () => {
    setGenerating(true)
    try {
      const res = await fetch(`${API}/thinking/generate`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setQuestions(data)
        setAnswers({})
        setShowAnswers({})
      }
    } catch (e) {
      console.error('Failed to generate questions:', e)
    } finally {
      setGenerating(false)
    }
  }

  const toggleAnswer = (idx) => {
    setShowAnswers(prev => ({ ...prev, [idx]: !prev[idx] }))
  }

  useEffect(() => {
    fetchQuestions()
  }, [])

  return (
    <div className="thinking-page">
      <div className="page-header">
        <h1>&#129504; 每日思考</h1>
        <p className="subtitle">{today} · 出海行业面试 Mock Interview</p>
      </div>

      <div className="intro-section">
        <p>每日推送 3 个关于行业出海相关的面试问题，帮助你准备 Overseas Sales 面试。</p>
        <p>每个问题都可以展开查看参考答案，助你深度思考。</p>
      </div>

      <div className="action-bar">
        <button
          className="btn btn-primary"
          onClick={generateQuestions}
          disabled={generating}
        >
          {generating ? '正在生成...' : '生成今日问题'}
        </button>
      </div>

      {loading ? (
        <div className="loading">加载中...</div>
      ) : questions.length === 0 ? (
        <div className="empty-state">
          <p>暂无问题数据</p>
          <p>点击"生成今日问题"按钮获取面试练习题</p>
        </div>
      ) : (
        <div className="questions-list">
          {questions.map((q, idx) => (
            <div key={idx} className="question-card">
              <div className="question-number">Q{idx + 1}</div>
              <h3 className="question-text">{q.question}</h3>
              {q.context && (
                <p className="question-context">{q.context}</p>
              )}
              <div className="question-actions">
                <button
                  className="btn btn-outline"
                  onClick={() => toggleAnswer(idx)}
                >
                  {showAnswers[idx] ? '隐藏参考答案' : '查看参考答案'}
                </button>
              </div>
              {showAnswers[idx] && q.answer && (
                <div className="answer-section">
                  <h4>参考答案要点：</h4>
                  <div className="answer-content">
                    {Array.isArray(q.answer) ? (
                      <ul>
                        {q.answer.map((point, i) => (
                          <li key={i}>{point}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>{q.answer}</p>
                    )}
                  </div>
                </div>
              )}
              {q.tips && (
                <div className="tips-section">
                  <span className="tips-icon">&#128161;</span>
                  <span className="tips-text">{q.tips}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="encouragement">
        <p>&#128170; 每日练习，持续进步！</p>
      </div>
    </div>
  )
}

export default Thinking