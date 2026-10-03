// Shared types used across the entire Aanandi widget

export type UIMode = 'idle' | 'chat' | 'voice' | 'modal';

export type CallStatus =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'ended';

export type WSStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  status: 'sending' | 'delivered' | 'error';
  timestamp: Date;
  toolPayload?: ToolPayload;
}

export type ToolPayloadType = 'calendar' | 'escrow';

export interface ToolPayload {
  type: ToolPayloadType;
  data?: Record<string, unknown>;
}

export interface LeadData {
  full_name?: string;
  email?: string;
  phone?: string;
  company?: string;
  brief?: string;
  session_id?: string;
}

export interface TimeSlot {
  start: string; // ISO 8601
  end: string;
  available: boolean;
}

export interface BookingPayload {
  slot_start: string;
  slot_end: string;
  lead_id: string;
  session_id: string;
}

export interface EscrowPayload {
  type: 'stripe' | 'usdc';
  amount: number;
  session_id: string;
  lead_id: string;
}

export interface WidgetConfig {
  apiBase: string;
  theme?: 'dark' | 'light';
}
