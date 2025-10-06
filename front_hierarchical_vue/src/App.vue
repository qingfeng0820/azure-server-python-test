<script>
    // 这些变量不会暴露给模板，是私有的
    let nextId = 1
    const MAX_CONVERSATION_LENGTH = 1000
    const API_SERVER = 'http://localhost:8000'
    //const API_SERVER = 'https://shmtest-ahepbqhwbbaxf3cy.eastasia-01.azurewebsites.net'
    const LOGIN_URL = API_SERVER + '/login'
    const LOGOUT_URL = API_SERVER + '/logout'
</script>
<script setup>
    import './App.css'
    import {ref, reactive, watch, nextTick, onMounted, onBeforeUnmount} from 'vue'

    let question = ref("")
    let conversation = reactive([])
    let isLoading = ref(false)
    let currentUser = ref(null)
    let conversationEndRef = ref(null)
    const requireLogin = true


    function scrollToAnchor(anchorRef) {
      anchorRef.value?.scrollIntoView({ behavior: 'smooth' })
    }

    function addQAPair(question, answer="") {
        const newConversation = {
            id: "conversation-" + nextId++,
            question: question,
            answer: answer ? answer : ""
        }

        if (conversation.length >= MAX_CONVERSATION_LENGTH) {
            // 保持最大长度，移除最早的对话
            conversation.splice(0, conversation - MAX_CONVERSATION_LENGTH + 1)
        }
        conversation.push(newConversation)
    }

    function appendAnswer(answer) {
      const lastIndex = conversation.length - 1
      if (lastIndex >= 0) {
        // 直接修改响应式数组中的元素
        conversation[lastIndex].answer += answer
      }
    }

    const abortController = ref(null)
    // 获取用户信息和对话历史
    async function fetchData () {
      try {
        abortController.value = new AbortController()
        const { signal } = abortController.value

        let userPromise = requireLogin
          ? fetch(API_SERVER + '/users/me', {
              method: 'GET',
              credentials: 'include',
              signal,
            })
          : Promise.resolve({ ok: false })

        // 并行执行两个请求
        const [userResponse, historyResponse] = await Promise.all([
          userPromise,
          fetch(API_SERVER + '/teams/chat/history', {
            method: 'GET',
            credentials: 'include',
            signal,
          })
        ])

        if (requireLogin) {
          if (userResponse.ok) {
            currentUser.value = await userResponse.json()
          } else {
            currentUser.value = null
          }
          if (userResponse.status === 401) {
            const redirectUri = encodeURIComponent(window.location.href)
            window.location.href = `${LOGIN_URL}?url=${redirectUri}`
          }
        }

        if (historyResponse.ok) {
          const conversationList = await historyResponse.json()
          conversation.value = []
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

    watch(conversation, () => {
        nextTick(() => {
            scrollToAnchor(conversationEndRef)
        })
    })


    // 组件挂载时执行
    onMounted(() => {
        fetchData()
    })

    // 组件卸载前执行清理
    onBeforeUnmount(() => {
      if (abortController.value) {
        abortController.value.abort()
      }
    })

    const handleLogout = async () => {
        if (currentUser) {
            // confirm logout
            if (!window.confirm('Confirm Logout?')) {
                return
            }
            try {
              const resp = await fetch(LOGOUT_URL, {
                method: 'GET',
                credentials: 'include',
              })
              if (resp.ok) {
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
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        if (!isLoading.value && question.value.trim() && (currentUser.value || !requireLogin)) {
          handleSubmit()
        }
      }
    }

    const handleSubmit = async () => {
      if (!question.value.trim()) return
      isLoading.value = true
      const q = question.value
      question.value = ""
      addQAPair(q)
      try {
        const response = await fetch(API_SERVER + '/teams/chat/ask', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({question: q}),
        })

        if (response.ok) {
            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            while (true) {
                const { done, value } = await reader.read()
                if (done) break
                const chunk = decoder.decode(value)
                appendAnswer(chunk)
            }
            reader.releaseLock()
        } else if (response.status === 401) {
            const redirectUri = encodeURIComponent(window.location.href)
            window.location.href = `${LOGIN_URL}?url=${redirectUri}`
        }
        isLoading.value = false
      } catch (error) {
        console.error('Error:', error)
      } finally {
        isLoading.value = false
      }
    }
</script>
<template>
      <div className="container">
        <div className="header">
          <h1 style="display: inline-block">Conversation</h1>

             <button
              className="logout-button"
              style="float: right; marginLeft: 20px; verticalAlign: middle"
              title="Click to logout"
              v-show="requireLogin"
              @click="handleLogout"
            >
              {{currentUser ? currentUser['username'] : 'LOGIN'}}
            </button>

        </div>

        <div className="response-section">
          <div className="response-content scroll-overflow" v-show="conversation.length > 0">
             <div v-for="qa in conversation" :key="qa.id" className="qa-pair">
                <div className="question-display auto-wrap">
                  <strong>Q:</strong> {{ qa.question }}
                </div>
                <div className="answer-display auto-wrap">
                  <strong>A:</strong> {{ qa.answer }}
                </div>
              </div>
              <div ref="conversationEndRef" />
          </div>
        </div>

        <div className="question-section">
          <h2>Ask a Question</h2>
          <textarea
            className="question-textarea"
            v-model="question"
            rows=3
            @keydown="handleKeyDown"
            placeholder="Enter your question here..."
          />
         </div>

        <div className="submit-section">
            <button
              className="submit-button"
              @click="handleSubmit"
              :disabled="isLoading || !question.trim() || (requireLogin && !currentUser)"
            >
              {{ isLoading ? 'Answering...' : 'Submit' }}
            </button>
        </div>
      </div>
</template>
<style scoped>
.logo {
  height: 6em;
  padding: 1.5em;
  will-change: filter;
  transition: filter 300ms;
}
.logo:hover {
  filter: drop-shadow(0 0 2em #646cffaa);
}
.logo.vue:hover {
  filter: drop-shadow(0 0 2em #42b883aa);
}
</style>
