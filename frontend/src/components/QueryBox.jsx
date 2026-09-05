import { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  Bot,
  ChevronDown,
  ChevronRight,
  SendHorizonal,
  Sparkles,
  User,
} from 'lucide-react';
import '../App.css';

const QUICK_PROMPTS = [
  'Which exceptions are tax mismatches and why?',
  'What happened to setl_100009RP?',
  'Show me unresolved settlements',
  'What is the total unreconciled amount?',
];

function formatAnswer(answer) {
  if (!answer) return [];

  return answer
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block, index) => {
      if (block.includes('|') && block.split('\n').length >= 2) {
        const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
        const rows = lines
          .filter((line) => line.includes('|'))
          .map((line) => line.split('|').map((cell) => cell.trim()).filter(Boolean))
          .filter((cells) => cells.length > 0);

        if (rows.length >= 2) {
          const header = rows[0];
          const body = rows.slice(2);
          return { type: 'table', header, body, key: `table-${index}` };
        }
      }

      if (block.startsWith('- ') || block.startsWith('* ')) {
        return {
          type: 'list',
          items: block.split('\n').map((line) => line.replace(/^[-*]\s*/, '').trim()).filter(Boolean),
          key: `list-${index}`,
        };
      }

      return { type: 'paragraph', text: block.replace(/\*\*/g, '').trim(), key: `p-${index}` };
    });
}

function AssistantAnswer({ text }) {
  const blocks = useMemo(() => formatAnswer(text), [text]);

  return (
    <div className="query-rich-answer">
      {blocks.map((block) => {
        if (block.type === 'table') {
          return (
            <div key={block.key} className="query-answer-table-wrap">
              <table className="query-answer-table">
                <thead>
                  <tr>
                    {block.header.map((cell, idx) => <th key={idx}>{cell}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {block.body.map((row, rowIdx) => (
                    <tr key={rowIdx}>
                      {row.map((cell, cellIdx) => <td key={cellIdx}>{cell.replace(/\*\*/g, '')}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (block.type === 'list') {
          return (
            <ul key={block.key} className="query-answer-list">
              {block.items.map((item, idx) => <li key={idx}>{item.replace(/\*\*/g, '')}</li>)}
            </ul>
          );
        }

        return <p key={block.key}>{block.text}</p>;
      })}
    </div>
  );
}

const QueryBox = ({ runId }) => {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showAuditTrail, setShowAuditTrail] = useState({});
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [typingMessageId, setTypingMessageId] = useState(null);
  const messageListRef = useRef(null);
  const bottomRef = useRef(null);
  const startTimeRef = useRef(null);

  useEffect(() => {
    const container = messageListRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    if (!loading) return undefined;

    const interval = window.setInterval(() => {
      const startedAt = startTimeRef.current || Date.now();
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    return () => window.clearInterval(interval);
  }, [loading]);

  useEffect(() => {
    if (!typingMessageId) return undefined;

    const interval = window.setInterval(() => {
      setMessages((current) => current.map((message) => {
        if (message.id !== typingMessageId || message.visibleText === message.fullText) {
          return message;
        }

        const nextLength = Math.min(message.visibleText.length + 6, message.fullText.length);
        return {
          ...message,
          visibleText: message.fullText.slice(0, nextLength),
          isStreaming: nextLength < message.fullText.length,
        };
      }));
    }, 30);

    return () => window.clearInterval(interval);
  }, [typingMessageId]);

  const assistantStatus = useMemo(() => {
    if (!loading) return '';
    if (elapsedSeconds < 4) return 'Reading this reconciliation...';
    if (elapsedSeconds < 10) return 'Checking records and exceptions...';
    if (elapsedSeconds < 15) return 'Reviewing evidence and tool results...';
    return 'Drafting the answer...';
  }, [elapsedSeconds]);

  const submitQuestion = async (rawQuestion) => {
    const trimmed = rawQuestion.trim();
    if (!trimmed) {
      setError('Please enter a question');
      return;
    }

    if (!runId) {
      setError('No run selected. Please run reconciliation first.');
      return;
    }

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: trimmed,
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion('');
    setLoading(true);
    setError(null);
    setElapsedSeconds(0);
    startTimeRef.current = Date.now();

    try {
      const response = await axios.post('http://127.0.0.1:8000/api/chat', {
        question: trimmed,
        run_id: runId,
      });

      const messageId = `assistant-${Date.now()}`;
      const answerText = response.data.answer || 'No answer returned.';
      const assistantMessage = {
        id: messageId,
        role: 'assistant',
        fullText: answerText,
        visibleText: elapsedSeconds >= 15 ? answerText.slice(0, 6) : '',
        isStreaming: true,
        sources: response.data.sources || [],
        auditTrail: response.data.audit_trail || [],
        toolRounds: response.data.tool_rounds || 0,
      };

      setMessages((current) => [...current, assistantMessage]);
      setShowAuditTrail((current) => ({ ...current, [messageId]: false }));
      setTypingMessageId(messageId);

      if (Date.now() - (startTimeRef.current || Date.now()) < 15000) {
        window.setTimeout(() => {
          setMessages((current) => current.map((message) => (
            message.id === messageId && !message.visibleText
              ? { ...message, visibleText: message.fullText.slice(0, 6) }
              : message
          )));
        }, 15000 - (Date.now() - (startTimeRef.current || Date.now())));
      }
    } catch (err) {
      setError(
        err.response?.data?.detail ||
        err.message ||
        'Failed to answer question'
      );
    } finally {
      setLoading(false);
      setElapsedSeconds(0);
    }
  };

  const handleAsk = async () => {
    await submitQuestion(question);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  return (
    <div className="query-chatbot ai-query-box">

      <div className="query-chatbot-body">
        {messages.length === 0 && !loading && (
          <div className="query-welcome-card">
            <div className="query-welcome-title">Ask about this reconciliation</div>
            <p className="query-welcome-copy">
              I can explain matches, list exceptions, summarize unresolved amounts, and show which records were used.
            </p>
            <div className="query-quick-prompts">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="query-quick-prompt"
                  onClick={() => submitQuestion(prompt)}
                  disabled={!runId || loading}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="query-message-list" ref={messageListRef}>
          {messages.map((message) => (
            <div key={message.id} className={`query-message-row query-message-row-${message.role}`}>
              <div className={`query-avatar query-avatar-${message.role}`}>
                {message.role === 'user' ? <User size={15} /> : <Bot size={15} />}
              </div>

              <div className={`query-bubble query-bubble-${message.role}`}>
                {message.role === 'user' ? (
                  <p className="query-user-text">{message.text}</p>
                ) : (
                  <>
                    <AssistantAnswer text={message.visibleText || ''} />
                    {message.isStreaming && <div className="query-streaming-caret" />}

                    {message.sources?.length > 0 && (
                      <div className="query-sources-inline">
                        <span className="query-inline-label">Sources</span>
                        <div className="sources-list">
                          {message.sources.map((source, idx) => (
                            <span key={idx} className="source-badge">{source}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {message.auditTrail?.length > 0 && (
                      <div className="query-audit">
                        <button
                          type="button"
                          className="query-audit-toggle"
                          onClick={() => setShowAuditTrail((current) => ({
                            ...current,
                            [message.id]: !current[message.id],
                          }))}
                        >
                          {showAuditTrail[message.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <span>Reasoning audit trail</span>
                          <span className="query-audit-meta">
                            {message.auditTrail.length} tool call(s) · {message.toolRounds} round(s)
                          </span>
                        </button>

                        {showAuditTrail[message.id] && (
                          <div className="query-audit-list">
                            {message.auditTrail.map((entry, idx) => (
                              <div key={idx} className="query-audit-item">
                                <div className="query-audit-title">{entry.tool}</div>
                                <div className="query-audit-block">
                                  <strong>Arguments</strong>
                                  <pre>{JSON.stringify(entry.arguments || {}, null, 2)}</pre>
                                </div>
                                <div className="query-audit-block">
                                  <strong>Result</strong>
                                  <pre>{JSON.stringify(entry.result || {}, null, 2)}</pre>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="query-message-row query-message-row-assistant">
              <div className="query-avatar query-avatar-assistant">
                <Bot size={15} />
              </div>
              <div className="query-bubble query-bubble-assistant query-bubble-thinking">
                <div className="query-thinking-title">{assistantStatus}</div>
                <div className="query-thinking-dots">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="query-thinking-sub">This can take a few seconds for deeper questions.</div>
              </div>
            </div>
          )}

          {error && (
            <div className="query-error-inline">
              <strong>Error:</strong> {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="query-composer">
        <div className="query-composer-input-wrap">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about an exception, payment, order, tax mismatch, or unreconciled amount..."
            className="query-composer-input"
            disabled={loading || !runId}
            rows="3"
          />
          <button
            onClick={handleAsk}
            className="query-send-button query-send-button-inside"
            disabled={loading || !runId || !question.trim()}
          >
            <SendHorizonal size={15} /> Send
          </button>
        </div>
      </div>

      {!runId && (
        <div className="query-placeholder">
          <p>Run reconciliation first to ask questions</p>
        </div>
      )}
    </div>
  );
};

export default QueryBox;
