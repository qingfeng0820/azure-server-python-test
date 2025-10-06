import { useState, useRef, useEffect } from 'react'
import './App.css'

function App() {
  const [question, setQuestion] = useState('')
  const conversationEndRef = useRef(null)
  const [conversation, setConversation] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [useStream, setUseStream] = useState(true)
  const [currentUser, setCurrentUser] = useState(null)
  const nextId = useRef(1)
  const MAX_CONVERSATION_LENGTH = 1000
  const requireLogin = true
  const API_SERVER = 'http://localhost:8000'
//  const API_SERVER = 'https://shmtest-ahepbqhwbbaxf3cy.eastasia-01.azurewebsites.net'
  const LOGIN_URL = API_SERVER + '/login'
  const LOGOUT_URL = API_SERVER + '/logout'

  const scrollToAnchor = (anchorRef) => {
    anchorRef.current?.scrollIntoView({ behavior: 'smooth' })
  }
  useEffect(() => {
     scrollToAnchor(conversationEndRef)
  }, [conversation])


  const addQAPair = (question, answer="") => {
    const newConversation = {
        id: "conversation-" + nextId.current++,
        question: question,
        answer: answer ? answer : ""
    }

    setConversation(prev => {
      if (prev.length >= MAX_CONVERSATION_LENGTH) {
        return [...prev.slice(-(MAX_CONVERSATION_LENGTH - 1)), newConversation]
      }
      return [...prev, newConversation]
    })
  }

  const appendAnswer = (answer) => {
    setConversation(prev => {
        const updated = [...prev]
        const lastIndex = updated.length - 1
        if (lastIndex >= 0) {
            updated[lastIndex] = {
                ...updated[lastIndex],
                answer: updated[lastIndex].answer + answer
            }
        }
        return updated
    })
  }

  useEffect(() => {
   const abortController = new AbortController()
   const { signal } = abortController
   const fetchData = async () => {
     try {

        let userPromise = requireLogin
          ? fetch(API_SERVER + '/users/me', {
            method: 'GET',
            credentials: 'include',
            signal,
          })
          : Promise.resolve({ ok: false });
       // 并行执行两个请求
       const [userResponse, historyResponse] = await Promise.all([
           userPromise,
           fetch(API_SERVER + '/ai/chat/history', {
             method: 'GET',
             credentials: 'include',
             signal,
           })
       ])
       if (requireLogin) {
           if (userResponse.ok) {
             setCurrentUser(await userResponse.json())
           } else {
             setCurrentUser(null)
           }
           if (userResponse.status === 401) {
              const redirectUri = encodeURIComponent(window.location.href)
              window.location.href = `${LOGIN_URL}?url=${redirectUri}`
           }
       }
       if (historyResponse.ok) {
         const conversationList = await historyResponse.json()
         setConversation([])
         conversationList.forEach(qa => {
           addQAPair(qa.question, qa.answer)
         })
       }
     } catch (error) {
       if (error.name !== 'AbortError') {
         console.error('Error:', error)
       }
     }
   }
   fetchData()
   return () => {
     abortController.abort()
   }
  }, [])

  const handleSubmit = async () => {
      if (!question.trim()) return
      const q = question.trim()
      setIsLoading(true)
      setQuestion("")
      addQAPair(q)
      try {
        const response = await fetch(API_SERVER + '/ai/chat/ask', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({question: q, stream: useStream}),
        })

        if (response.ok) {
            if (useStream) {
                const reader = response.body.getReader()
                const decoder = new TextDecoder()

                while (true) {
                    const { done, value } = await reader.read()
                    if (done) break
                    const chunk = decoder.decode(value)
                    appendAnswer(chunk)
                }

                reader.releaseLock()
            } else {
                const data = await response.json()
                const answer = data.answer || data.response || data.toString()
                appendAnswer(answer)
            }
        } else if (response.status === 401) {
            const redirectUri = encodeURIComponent(window.location.href)
            window.location.href = `${LOGIN_URL}?url=${redirectUri}`
        }
        setIsLoading(false)
      } catch (error) {
        console.error('Error:', error)
      } finally {
        setIsLoading(false)
      }
  }

  return (
    <>
    <div className="App">
      <div className="container">
        <div className="header">
          <h1 style={{ display: 'inline-block' }}>Conversation</h1>
            {requireLogin && (
             <button
              className="logout-button"
              onClick={async () => {
                if (currentUser) {
                    // confirm logout
                    if (!confirm('Confirm Logout?')) {
                        return
                    }
                    try {
                      const resp = await fetch(LOGOUT_URL, {
                        method: 'GET',
                        credentials: 'include',
                      })
                      if (resp.ok) {
//                        setCurrentUser(null)
//                        setConversation([])
//                        setQuestion("")
                        const redirectUri = encodeURIComponent(window.location.href)
                        window.location.href = `${LOGIN_URL}?url=${redirectUri}`
                      }
                    } catch (error) {
                      console.error('Logout failed:', error)
                    }
                } else {
                    const redirectUri = encodeURIComponent(window.location.href)
                    window.location.href = `${LOGIN_URL}?url=${redirectUri}`
                }
              }}
              style={{
                float: 'right',
                marginLeft: '20px',
                verticalAlign: 'middle'
              }}
              title="Click to logout"
            >
              {currentUser ? currentUser['username'] : 'LOGIN'}
            </button>
          )}
        </div>
        {/*MASK*/}
        {/*isLoading && <div className="loading">Loading...</div>*/}
        <div className="response-section">
          <div className="response-content scroll-overflow" style={{ visibility: conversation.length > 0 ? 'visible' : 'hidden' }}>
              {conversation.map((qa) => (
                <div className="qa-pair" key={qa.id}>
                  <div className="question-display auto-wrap">
                    <strong>Q:</strong> {qa.question}
                  </div>
                  <div className="answer-display auto-wrap">
                    <strong>A:</strong> {qa.answer}
                  </div>
                </div>
              ))}
              <div ref={conversationEndRef} />
          </div>
        </div>

        <div className="question-section">
          <h2>Ask a Question</h2>
          <textarea
            className="question-textarea"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  if (!isLoading.value && question.trim() && (currentUser || !requireLogin)) {
                    handleSubmit()
                  }
                }
            }}
            rows={3}
            placeholder="Enter your question here..."
          />
          <label>
            <input
              type="checkbox"
              checked={useStream}
              onChange={(e) => setUseStream(e.target.checked)}
            />
            Stream Response
          </label>
         </div>

        <div className="submit-section">
            <button
              className="submit-button"
              onClick={handleSubmit}
              disabled={isLoading || !question.trim() || (requireLogin && !currentUser)}
            >
              {isLoading ? 'Answering...' : 'Submit'}
            </button>
        </div>
      </div>
    </div>
    </>
  )
}

export default App
