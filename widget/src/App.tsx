import React, { useState, useCallback, useRef } from 'react';
import type { UIMode, Message, WidgetConfig } from './types';
import ChatLauncher from './components/ChatLauncher';
import ChatWindow from './components/ChatWindow';
import CallAIWidget from './components/CallAIWidget';
import { useSessionStorage } from './hooks/useSessionStorage';
import { useWebSocket } from './hooks/useWebSocket';

interface AppProps {
  config: WidgetConfig;
}

export default function App({ config }: AppProps) {
  const { sessionId, leadId } = useSessionStorage();

  // ── UI state ──────────────────────────────────────────────────
  const [uiMode, setUiMode] = useState<UIMode>('idle');
  const [unreadCount, setUnreadCount] = useState(0);

  // ── Messages ──────────────────────────────────────────────────
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome-1',
      role: 'assistant',
      content:
        "👋 Hi! I'm **Aanandi**, your AI Sales Engineer. I can help answer product questions, verify your details, and guide you through booking a discussion with our team.\n\nHow can I help you today?",
      status: 'delivered',
      timestamp: new Date(),
    },
  ]);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // ── WebSocket chat ─────────────────────────────────────────────
  const { sendMessage: wsSend, status: wsStatus, latency } = useWebSocket({
    apiBase: config.apiBase,
    sessionId,
    enabled: uiMode === 'chat',
    onMessage: (msg: Message) => {
      setMessages((prev) => [...prev, msg]);
      if (uiMode !== 'chat') setUnreadCount((c) => c + 1);
    },
  });

  // ── Handlers ──────────────────────────────────────────────────
  const openChat = useCallback(() => {
    setUiMode('chat');
    setUnreadCount(0);
  }, []);

  const closeChat = useCallback(() => {
    setUiMode('idle');
  }, []);

  const openVoice = useCallback(() => {
    setUiMode('voice');
  }, []);

  const endVoice = useCallback(() => {
    setUiMode('chat');
  }, []);

  const handleSendMessage = useCallback(
    async (text: string) => {
      if (!text.trim()) return;

      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text.trim(),
        status: 'sending',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);

      try {
        await wsSend(text.trim());
        setMessages((prev) =>
          prev.map((m) =>
            m.id === userMsg.id ? { ...m, status: 'delivered' } : m,
          ),
        );
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === userMsg.id ? { ...m, status: 'error' } : m,
          ),
        );
      }
    },
    [wsSend],
  );

  // ── Render ────────────────────────────────────────────────────
  return (
    <>
      {/* Floating crystal launcher */}
      <ChatLauncher
        uiMode={uiMode}
        unreadCount={unreadCount}
        onClick={uiMode === 'idle' ? openChat : closeChat}
      />

      {/* Chat window */}
      {uiMode === 'chat' && (
        <ChatWindow
          messages={messages}
          wsStatus={wsStatus}
          latency={latency}
          sessionId={sessionId}
          leadId={leadId}
          apiBase={config.apiBase}
          onSendMessage={handleSendMessage}
          onOpenVoice={openVoice}
          onClose={closeChat}
        />
      )}

      {/* Voice call widget — unmounts on end and restores ChatWindow */}
      {uiMode === 'voice' && (
        <CallAIWidget
          sessionId={sessionId}
          apiBase={config.apiBase}
          onEnd={endVoice}
        />
      )}
    </>
  );
}
