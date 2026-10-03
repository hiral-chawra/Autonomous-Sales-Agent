import { useCallback, useEffect, useRef, useState } from 'react';

const SESSION_KEY = 'aanandi_session_id';
const LEAD_KEY    = 'aanandi_lead_id';
const THREAD_KEY  = 'aanandi_thread_id';

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function getOrCreate(key: string): string {
  try {
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const fresh = generateId();
    sessionStorage.setItem(key, fresh);
    return fresh;
  } catch {
    // Private browsing fallback
    return generateId();
  }
}

function persist(key: string, value: string) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

/**
 * Persists sessionId, leadId, threadId across tab refreshes via sessionStorage.
 * Returns hydrated values and setters.
 */
export function useSessionStorage() {
  const [sessionId]          = useState<string>(() => getOrCreate(SESSION_KEY));
  const [leadId, setLeadIdState]   = useState<string | null>(() => {
    try { return sessionStorage.getItem(LEAD_KEY); } catch { return null; }
  });
  const [threadId, setThreadIdState] = useState<string | null>(() => {
    try { return sessionStorage.getItem(THREAD_KEY); } catch { return null; }
  });

  const setLeadId = useCallback((id: string) => {
    persist(LEAD_KEY, id);
    setLeadIdState(id);
  }, []);

  const setThreadId = useCallback((id: string) => {
    persist(THREAD_KEY, id);
    setThreadIdState(id);
  }, []);

  return { sessionId, leadId, threadId, setLeadId, setThreadId };
}
