import { useState, useRef, useEffect } from 'react'

/**
 * ARGUSCopilot — LLM-powered assistant for District Magistrates.
 * 
 * Embedded in dashboard bottom-right. Connects to /api/v1/copilot/chat.
 * Shows suggested questions, tool call indicators, and streaming responses.
 */

const SUGGESTED_QUESTIONS = [
  "Time before Majuli Ward 7 floods?",
  "Which road closes first?",
  "Evacuation plan — how many buses?",
  "Open dam gate — downstream impact?",
  "Send EMERGENCY alert to Ward 7",
]

const COPILOT_API = import.meta.env.VITE_COPILOT_URL || ''

export default function ARGUSCopilot({ district = 'Majuli', userRole = 'DISTRICT_MAGISTRATE' }) {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Good evening. I'm watching **${district}** district. Current status: 2 villages at WATCH level, 1 at WARNING. What do you need to know?`,
      tools: [],
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input when opened
  useEffect(() => {
    if (isOpen) inputRef.current?.focus()
  }, [isOpen])

  const sendMessage = async () => {
    const trimmed = input.trim()
    if (!trimmed || loading) return

    const userMsg = { role: 'user', content: trimmed, tools: [] }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const r = await fetch(`${COPILOT_API}/api/v1/copilot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          history: messages.map(m => ({ role: m.role, content: m.content })),
          user_role: userRole,
          district,
          demo_mode: true,
        }),
      })

      if (!r.ok) throw new Error(`HTTP ${r.status}`)

      const data = await r.json()
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        tools: data.tools_used || [],
        responseTime: data.response_time_ms,
      }])
    } catch (err) {
      console.error('Copilot error:', err)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Connection to ARGUS services lost. Retrying...',
        tools: [],
        error: true,
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // Render markdown-like bold text
  const renderContent = (text) => {
    if (!text) return null
    const parts = text.split(/(\*\*.*?\*\*)/g)
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="text-cyan-300 font-bold">{part.slice(2, -2)}</strong>
      }
      // Handle newlines
      return part.split('\n').map((line, j) => (
        <span key={`${i}-${j}`}>
          {j > 0 && <br />}
          {line}
        </span>
      ))
    })
  }

  // Floating button when closed
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 z-50 w-14 h-14 rounded-full
                   bg-gradient-to-br from-cyan-500 to-blue-600
                   shadow-lg shadow-cyan-900/40 hover:shadow-cyan-500/40
                   flex items-center justify-center transition-all
                   hover:scale-110 active:scale-95"
        title="Open ARGUS Copilot"
      >
        <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
        {/* Notification dot */}
        <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500
                         border-2 border-slate-900 animate-pulse" />
      </button>
    )
  }

  return (
    <div className="fixed bottom-4 right-4 w-[420px] max-h-[600px] z-50
                    bg-slate-900 rounded-2xl border border-cyan-400/30
                    shadow-2xl shadow-cyan-900/20 flex flex-col overflow-hidden">

      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700/50
                      bg-gradient-to-r from-slate-900 to-slate-800">
        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        <span className="text-cyan-400 font-bold text-sm tracking-wide">ARGUS Copilot</span>
        <span className="text-slate-500 text-[10px] ml-1">v2.0 • Claude Opus</span>
        <button
          onClick={() => setIsOpen(false)}
          className="ml-auto text-slate-500 hover:text-white transition-colors p-1"
          title="Close"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 min-h-[300px] max-h-[400px]">
        {messages.map((msg, i) => (
          <div key={i} className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            {/* Tool indicators */}
            {msg.tools && msg.tools.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {msg.tools.map(tool => (
                  <span key={tool} className="text-[9px] px-1.5 py-0.5 rounded-full
                    bg-cyan-900/50 text-cyan-400 border border-cyan-800/50">
                    {tool.replace('get_', '').replace('compute_', '').replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
            <div className={`max-w-[90%] rounded-xl px-3 py-2 text-sm leading-relaxed
              ${msg.role === 'user'
                ? 'bg-cyan-600/90 text-white'
                : msg.error
                  ? 'bg-red-900/30 text-red-300 border border-red-800/50'
                  : 'bg-slate-800/80 text-slate-200 border border-slate-700/30'
              }`}>
              {renderContent(msg.content)}
            </div>
            {msg.responseTime && (
              <span className="text-[9px] text-slate-600">{msg.responseTime.toFixed(0)}ms</span>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-start gap-2">
            <div className="bg-slate-800/80 rounded-xl px-3 py-2 text-sm text-slate-400
                            border border-slate-700/30">
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested questions */}
      <div className="px-3 py-2 flex gap-1.5 flex-wrap border-t border-slate-800/50">
        {SUGGESTED_QUESTIONS.slice(0, 3).map(q => (
          <button
            key={q}
            onClick={() => { setInput(q); inputRef.current?.focus() }}
            className="text-[10px] bg-slate-800/60 text-cyan-400/80 px-2 py-1
                       rounded-lg hover:bg-slate-700/60 hover:text-cyan-300
                       transition-colors border border-slate-700/30"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="p-3 pt-1 flex gap-2">
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about flood risk, evacuation, interventions..."
          className="flex-1 bg-slate-800/60 text-white text-sm rounded-lg px-3 py-2.5
                     border border-slate-700/50 focus:border-cyan-400/60
                     outline-none placeholder-slate-500 transition-colors"
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700
                     disabled:text-slate-500 text-white px-4 py-2.5
                     rounded-lg font-bold transition-colors text-sm"
        >
          →
        </button>
      </div>
    </div>
  )
}
