import React, { useState } from 'react';
import axios from 'axios';
import '../App.css';

/**
 * QueryBox -- QA interface for asking natural language questions about a run
 * 
 * Features:
 * - Text input for questions
 * - Submit button
 * - Displays LLM answer with cited source IDs
 * - Graceful error handling
 */
const QueryBox = ({ runId }) => {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAsk = async () => {
    if (!question.trim()) {
      setError('Please enter a question');
      return;
    }

    if (!runId) {
      setError('No run selected. Please run reconciliation first.');
      return;
    }

    setLoading(true);
    setError(null);
    setAnswer(null);
    setSources([]);

    try {
      const response = await axios.post('http://localhost:8000/ask', {
        question: question.trim(),
        run_id: runId,
      });

      setAnswer(response.data.answer);
      setSources(response.data.sources || []);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
        err.message ||
        'Failed to answer question'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  return (
    <div className="query-box-container">
      <div className="query-box-header">
        <h3>Ask About This Run</h3>
        <p>Ask questions about matches, exceptions, and investigations</p>
      </div>

      <div className="query-input-wrapper">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="e.g., What happened to settlement setl_100002RP? or How many exceptions are in this run?"
          className="query-input"
          disabled={loading || !runId}
          rows="3"
        />
        <button
          onClick={handleAsk}
          className="query-button"
          disabled={loading || !runId || !question.trim()}
        >
          {loading ? 'Asking...' : 'Ask'}
        </button>
      </div>

      {error && (
        <div className="query-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {answer && (
        <div className="query-result">
          <div className="query-answer">
            <strong>Answer:</strong>
            <p>{answer}</p>
          </div>

          {sources && sources.length > 0 && (
            <div className="query-sources">
              <strong>Sources:</strong>
              <div className="sources-list">
                {sources.map((source, idx) => (
                  <span key={idx} className="source-badge">
                    {source}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!runId && (
        <div className="query-placeholder">
          <p>Run reconciliation first to ask questions</p>
        </div>
      )}
    </div>
  );
};

export default QueryBox;
