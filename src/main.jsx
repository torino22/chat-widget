// src/main.jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import Chat from './Chat'
import './Chat.css'

function loadChatWidget() {
  const container = document.createElement('div')
  container.id = 'chat-widget-container'
  document.body.appendChild(container)
  ReactDOM.createRoot(container).render(<Chat />)
}

// Automatically run it when script is loaded
loadChatWidget()

// Also expose a manual trigger for flexibility
window.loadChatWidget = loadChatWidget
