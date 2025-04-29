import React, { useState, useRef, useEffect } from 'react';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { AdapterLuxon } from '@mui/x-date-pickers/AdapterLuxon';
import TextField from '@mui/material/TextField';
import { DateTime } from 'luxon';
import axios from 'axios';
import './Chat.css';

export default function Chat() {
  const [isOpen, setIsOpen] = useState(false);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [messages, setMessages] = useState([{ id: 1, text: "Hello! I am your Onboarding Companion", isAI: true }]);
  const [input, setInput] = useState('');
  const [selectedDateTime, setSelectedDateTime] = useState(DateTime.now());
  const messagesEndRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const toggleChat = () => {
    setIsOpen(prev => !prev);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (input.trim() === '') return;

    try {
      const response = await axios.post("http://localhost:8000/api/message", {
        prompt: input,
        conversationHistory: conversationHistory,
      });

      const { conversationHistory: updatedHistory } = response.data;
      setConversationHistory(updatedHistory);

      const displayHistory =
        updatedHistory.length > 0 && updatedHistory[0].role === 'system'
          ? updatedHistory.slice(1)
          : updatedHistory;

      const newMessages = displayHistory.map((msg, index) => ({
        id: index + 1,
        text: msg.content,
        isAI: msg.role === "assistant"
      }));
      newMessages.unshift({ id: 1, text: "Hello! I am your Onboarding Companion", isAI: true })
      setMessages(newMessages);
      if (
        newMessages.length >= 3 &&
        newMessages[newMessages.length - 1].text.includes("Thank you for your time")
      ) {
        const confirmationText = newMessages[newMessages.length - 3].text;

        const cleanedConfirmation = confirmationText.replace(/^'+|'+$/g, "");

        const lines = cleanedConfirmation.split("\n").map(line => line.trim());
        let details = {};
        lines.slice(1).forEach(line => {
          const parts = line.split(":");
          if (parts.length >= 2) {
            const key = parts[0].trim().toLowerCase();
            const value = parts.slice(1).join(":").trim();
            details[key] = value;
          }
        });

        axios
          .post("http://localhost:8000/api/leads", {
            name: details.name,
            email: details.email,
            requirement: details.requirement,
            company: details.company,
            phone: details.phone,
            meetingslot: ((DateTime.fromISO(details.meeting)).setZone("Asia/Kolkata")).toISO(),
          })
          .then(() => {
            // build the Zoom‐meeting payload:
            const meetingPayload = {
              start_time: selectedDateTime.setZone("Asia/Kolkata").toISO(),
              timezone: "Asia/Kolkata",
              topic: details.requirement,
              type: 2,
              agenda: details.requirement,
              duration: 30,
              settings: {
                meeting_invitees: [
                  { email: details.email }
                ],
                email_notification: true,
                contact_email: details.email,
                contact_name: details.name
              }
            };

            // call your FastAPI endpoint:
            return axios.post(
              "http://localhost:8000/zoom/create_meeting",
              meetingPayload
            );
          })
          .then(response => console.log(response.data))
          .catch(error => console.error(error));
      }

      // Clear the input after submission.
      setInput('');
    } catch (error) {
      console.error("❌ Error during API call:", error);
    }
  };



  const lastMsg = messages[messages.length - 1]?.text || '';
  const lower = lastMsg.toLowerCase();
  const mustHave = ["choose", "date", "slot"];
  const hasKeyword = mustHave.some(word => lower.includes(word));
  const hasConfirm = lower.includes("confirm");

  const showPicker = hasKeyword && !hasConfirm;

  return (
    <div className="chat-widget-container">
      
        <button className={`chat-toggle-button ${isOpen ? 'open' : ''}`} onClick={toggleChat}>
          <span className="chat-icon">💬</span>
        </button>
      
        <div className={`chat-box ${isOpen ? 'open' : ''}`}>
          <div className="chat-header">
            <div className="chat-title">Savvy Suave</div>
            <button className="close-button" onClick={toggleChat}>x</button>
          </div>
          <div ref={containerRef} className="chat-messages-area">
            {messages.map((message) => (
              <div
                key={message.id}
                className={message.isAI ? "chat-message-row ai" : "chat-message-row user"}
              >
                <div className={message.isAI ? "chat-message ai-message" : "chat-message user-message"}>
                  {message.text}
                </div>
              </div>
            ))}
            {showPicker && (
              <div className="chat-message-row user">
                <div className="chat-message user-message">
                <LocalizationProvider dateAdapter={AdapterLuxon}>
  <DateTimePicker
    label="Select date & time"
    value={selectedDateTime}
    onChange={(newValue) => {
      if (newValue) {
        const isoDate = newValue.toISODate();     // strips off time
        setInput(isoDate);
        setSelectedDateTime(newValue);
      }
    }}
    renderInput={(params) => <TextField {...params} />}
    minDateTime={DateTime.now()}
  />
</LocalizationProvider>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-area">
            <form onSubmit={handleSubmit} className="chat-input-form">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="chat-message-input"
                readOnly={showPicker}
                placeholder="Type your message..."
              />
              <button type="submit" className="chat-send-button">Send</button>
            </form>
          </div>
        </div>
      
    </div>
  );
}