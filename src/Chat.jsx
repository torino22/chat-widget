import React, { useState, useRef, useEffect } from 'react';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { AdapterLuxon } from '@mui/x-date-pickers/AdapterLuxon';
import TextField from '@mui/material/TextField';
import { FaPhone, FaPhoneSlash } from "react-icons/fa"; 
import { DateTime } from 'luxon';
import axios from 'axios';
import './Chat.css';

export default function Chat() {
  const [isOpen, setIsOpen] = useState(false);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [messages, setMessages] = useState([{ id: 1, text: "Hello! I am your Onboarding Companion", isAI: true }]);
  const [input, setInput] = useState('');
  const [selectedDateTime, setSelectedDateTime] = useState(DateTime.now());
  const [recording, setRecording] = useState(false);
  const messagesEndRef = useRef(null);
  const containerRef = useRef(null);
  const processingRef = useRef(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const [audioURL, setAudioURL] = useState(null);
  const silenceTimeoutRef = useRef(null);
  const [calling, setCalling] = useState(false);
  const [processingTranscript, setProcessingTranscript] = useState(false);
  const lastStopTsRef = useRef(0);

  const toggleCall = () => {
    setRecording(prev => !prev);
    if (mediaRecorderRef.current?.state === 'recording') stopRecording();
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const toggleChat = () => {
    setIsOpen(prev => !prev);
  };

  const sendTranscript = async (text) => {
    if (!text || text.trim() === '') {
      setProcessingTranscript(false);
      return;
    }
    
    setProcessingTranscript(true);
    try {
      const response = await axios.post("https://9911-35-240-155-137.ngrok-free.app/api/message", {
        prompt: text,
        conversationHistory: conversationHistory,
      });
      console.log(response.data)
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
      const aiOnly = newMessages.filter(m => m.isAI);
      const lastAI = aiOnly.pop();     // undefined if none
      if (lastAI) {
        await sendToTTS(lastAI.text);
        
        // usage: after you setMessages(…), just call:
       // speak(lastAI.text);
         }     
      
    } catch (err) {
      console.error('Failed to send transcript:', err);
    } finally {
      
    }
  };
   
  const sendToTTS = async (text) => {
    try {
      setProcessingTranscript(true)
      const response = await axios.post('https://9911-35-240-155-137.ngrok-free.app/tts/', {
        text: text,  // The AI response text to be converted to speech
        voice: "en-US-JennyNeural"  // You can set the voice dynamically or statically
      }, { responseType: 'blob' });  // Expecting a file (audio)
  
      const audioUrl = URL.createObjectURL(response.data); // Convert the blob to a URL
      await new Promise(resolve => {
        const audio = new Audio(audioUrl);
        audio.onended = resolve;   // resolve when playback finishes
        audio.play();
      });
      setProcessingTranscript(false)
  
    } catch (error) {
      console.error('Error sending text to TTS:', error);
      setProcessingTranscript(false)
    }
  };
  
  // Function to play the audio (you can use HTML audio tag or any other method)
  const playAudio = (audioUrl) => {
    const audio = new Audio(audioUrl);
    audio.play();
  };

  useEffect(() => {
    if(!recording) return;
    
    let stream, audioContext, analyser, dataArray, animationFrame;
    const preferred = 'audio/webm;codecs=opus';
    const options = MediaRecorder.isTypeSupported(preferred)
      ? { mimeType: preferred }
      : {};

    const setupAudio = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);
        dataArray = new Uint8Array(analyser.frequencyBinCount);

        mediaRecorderRef.current = new MediaRecorder(stream, options);

        // Collect audio data on dataavailable event
        mediaRecorderRef.current.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            audioChunksRef.current.push(e.data);
          }
        };

        // Process audio when recording stops
        mediaRecorderRef.current.onstop = async () => {
          // Skip if no data or already processing
          if (audioChunksRef.current.length === 0) {
            setProcessingTranscript(false);
            return;
          }
          
          // Lock processing
          setProcessingTranscript(true);
          
          try {
            // Create a blob from all chunks
            const audioBlob = new Blob(audioChunksRef.current, {
              type: mediaRecorderRef.current.mimeType
            });
            
            // Update audio preview
            const url = URL.createObjectURL(audioBlob);
            if (audioURL) URL.revokeObjectURL(audioURL);
            setAudioURL(url);
            
            // Upload and transcribe
            const form = new FormData();
            form.append('file', audioBlob, 'recording.webm');
            const { data } = await axios.post(
              'https://9911-35-240-155-137.ngrok-free.app/transcribe/',
              form,
              { headers: { 'Content-Type': 'multipart/form-data' } }
            );
            
            // Process the transcript if we got text back
            if (data && data.text) {
              await sendTranscript(data.text);
            } else {
              setProcessingTranscript(false);
            }
          } catch (err) {
            console.error('Audio processing failed:', err);
            setProcessingTranscript(false);
          } finally {
            // Reset for next recording
          
            audioChunksRef.current = [];
          }
        };

        const VOICE_THRESHOLD = 30; // Adjust based on testing
        const SILENCE_DURATION = 800; // ms of silence before stopping

        const detectAudio = () => {
          if (!recording || processingTranscript) return; 
          
          animationFrame = requestAnimationFrame(detectAudio);
          analyser.getByteFrequencyData(dataArray);
          const avg = dataArray.reduce((sum, v) => sum + v, 0) / dataArray.length;
          
          console.log(mediaRecorderRef.current?.state)

          // Only allow recording if we're not currently processing a transcript
          if (avg > VOICE_THRESHOLD &&
              mediaRecorderRef.current?.state === 'inactive' &&
              !processingTranscript) {
                clearTimeout(silenceTimeoutRef.current);
                console.log(avg)
                console.log(mediaRecorderRef.current?.state)
            // Voice detected and not recording - start recording
            audioChunksRef.current = [];
            mediaRecorderRef.current.start();
            setCalling(true);
          } else if (avg <= VOICE_THRESHOLD &&
                    mediaRecorderRef.current?.state === 'recording') {
            // Silence detected while recording - set timeout to stop
            console.log('aa')
            console.log(avg)
                console.log(mediaRecorderRef.current?.state)

            silenceTimeoutRef.current = setTimeout(() => {
              if (mediaRecorderRef.current?.state === 'recording') {
                // First set processing to true BEFORE stopping
                
                setProcessingTranscript(true);
                mediaRecorderRef.current.stop();
                

                setCalling(false);
                lastStopTsRef.current = Date.now();
              }
            }, SILENCE_DURATION);
          } else if (avg > VOICE_THRESHOLD && 
                    mediaRecorderRef.current?.state === 'recording') {
            // Voice detected while recording - clear timeout
            console.log(avg)
                console.log(mediaRecorderRef.current?.state)
            clearTimeout(silenceTimeoutRef.current);
          }
        };

        detectAudio();
      } catch (err) {
        console.error('Error accessing microphone:', err);
      }
    };

    setupAudio();

    return () => {

      cancelAnimationFrame(animationFrame);
      audioContext?.close();
      stream?.getTracks().forEach(t => t.stop());
      // Make sure we stop any ongoing recording
      if (mediaRecorderRef.current?.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
    };
  }, [recording, processingTranscript]);

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      // First set processing to true BEFORE stopping
      setProcessingTranscript(true);
      mediaRecorderRef.current.stop();
      lastStopTsRef.current = Date.now();
      setCalling(false);
      clearTimeout(silenceTimeoutRef.current);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (input.trim() === '') return;

    try {
      const response = await axios.post("https://9911-35-240-155-137.ngrok-free.app/api/message", {
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
              <button
            type="button"
            onClick={toggleCall}
            style={{
              padding: "8px 16px",
              fontSize: "14px",
              borderRadius: "24px",
              border: "none",
              backgroundColor: recording ? "#e74c3c" : "#2ecc71",
              color: "white",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "1px",
              marginLeft: '2px'
            }}
          >
            {recording ? <FaPhoneSlash /> : <FaPhone />}

          </button>
            </form>
          </div>
        </div>
      
    </div>
  );
}