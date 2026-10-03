import React, { useEffect, useState, useCallback } from 'react';
import { Calendar, ChevronLeft, ChevronRight, Clock, CheckCircle, AlertCircle, Zap, Shield } from 'lucide-react';
import type { ToolPayload, TimeSlot, BookingPayload, EscrowPayload } from '../types';

interface ActionCardsProps {
  payload: ToolPayload;
  sessionId: string;
  leadId: string | null;
  apiBase: string;
}

export default function ActionCards({ payload, sessionId, leadId, apiBase }: ActionCardsProps) {
  if (payload.type === 'calendar') {
    return (
      <CalendarCard
        sessionId={sessionId}
        leadId={leadId}
        apiBase={apiBase}
      />
    );
  }
  if (payload.type === 'escrow') {
    return (
      <EscrowCard
        sessionId={sessionId}
        leadId={leadId}
        apiBase={apiBase}
      />
    );
  }
  return null;
}

/* ══════════════════════════════════════════════════════════════════════
   CALENDAR CARD
══════════════════════════════════════════════════════════════════════ */
type CalendarState = 'loading' | 'picking' | 'confirming' | 'booked' | 'error';

function CalendarCard({
  sessionId,
  leadId,
  apiBase,
}: {
  sessionId: string;
  leadId: string | null;
  apiBase: string;
}) {
  const [state, setState] = useState<CalendarState>('loading');
  const [slots, setSlots] = useState<TimeSlot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [bookingUrl, setBookingUrl] = useState<string>('');
  const [weekOffset, setWeekOffset] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');

  // Fetch availability
  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(
          `${apiBase}/api/v1/scheduling/availability?session_id=${sessionId}&week_offset=${weekOffset}`,
        );
        if (!res.ok) throw new Error('Failed to fetch');
        const data: { slots: TimeSlot[] } = await res.json();
        setSlots(data.slots.filter((s) => s.available));
        setState('picking');
      } catch {
        // Show demo slots on error (dev mode)
        setSlots(generateDemoSlots());
        setState('picking');
      }
    };
    setState('loading');
    load();
  }, [apiBase, sessionId, weekOffset]);

  const handleBook = async () => {
    if (!selectedSlot) return;
    setState('confirming');
    try {
      const payload: BookingPayload = {
        slot_start: selectedSlot.start,
        slot_end: selectedSlot.end,
        lead_id: leadId ?? 'anonymous',
        session_id: sessionId,
      };
      const res = await fetch(`${apiBase}/api/v1/scheduling/book`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Booking failed');
      const data = await res.json();
      setBookingUrl(data.meeting_url ?? '#');
      setState('booked');
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'Unknown error');
      setState('error');
    }
  };

  // ── Render states ──────────────────────────────────────────────
  if (state === 'loading') {
    return (
      <CardShell title="Schedule a Demo" icon={<Calendar size={14} />}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '20px' }}>
          <div
            style={{
              width: '24px', height: '24px',
              border: '2px solid rgba(149,145,244,0.2)',
              borderTopColor: '#9591F4',
              borderRadius: '50%',
            }}
            className="animate-spin"
          />
        </div>
      </CardShell>
    );
  }

  if (state === 'booked') {
    return (
      <CardShell title="Booking Confirmed!" icon={<CheckCircle size={14} color="#22C55E" />}>
        <div style={{ textAlign: 'center', padding: '8px 0' }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎉</div>
          <p style={{ fontSize: '12px', color: '#DBD7FA', marginBottom: '10px', lineHeight: '1.5' }}>
            Your demo is confirmed! Check your email for the calendar invite.
          </p>
          {bookingUrl && bookingUrl !== '#' && (
            <a
              href={bookingUrl}
              target="_blank"
              rel="noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '7px 14px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #5A5BBD, #9591F4)',
                color: 'white',
                fontSize: '12px',
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              View Meeting Link →
            </a>
          )}
        </div>
      </CardShell>
    );
  }

  if (state === 'error') {
    return (
      <CardShell title="Schedule a Demo" icon={<AlertCircle size={14} color="#EF4444" />}>
        <p style={{ fontSize: '12px', color: '#EF4444', textAlign: 'center' }}>{errorMsg}</p>
        <button
          onClick={() => setState('picking')}
          style={{
            marginTop: '8px', width: '100%', padding: '8px', borderRadius: '8px',
            background: 'rgba(149,145,244,0.15)', border: '1px solid rgba(149,145,244,0.3)',
            color: '#9591F4', fontSize: '12px', cursor: 'pointer',
          }}
        >
          Try again
        </button>
      </CardShell>
    );
  }

  // Group slots by date
  const byDate = slots.reduce<Record<string, TimeSlot[]>>((acc, slot) => {
    const date = new Date(slot.start).toLocaleDateString('en-IN', {
      weekday: 'short', month: 'short', day: 'numeric',
    });
    if (!acc[date]) acc[date] = [];
    acc[date].push(slot);
    return acc;
  }, {});

  const dates = Object.keys(byDate);

  return (
    <CardShell title="Schedule a Demo" icon={<Calendar size={14} />}>
      {/* Week navigation */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
        <button
          onClick={() => setWeekOffset((w) => Math.max(0, w - 1))}
          disabled={weekOffset === 0}
          style={{
            width: '26px', height: '26px', borderRadius: '7px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: weekOffset === 0 ? 'transparent' : 'rgba(149,145,244,0.1)',
            border: '1px solid rgba(149,145,244,0.2)',
            cursor: weekOffset === 0 ? 'not-allowed' : 'pointer',
            color: weekOffset === 0 ? 'rgba(149,145,244,0.3)' : '#9591F4',
          }}
        >
          <ChevronLeft size={14} />
        </button>
        <span style={{ fontSize: '11px', color: '#C0CAC7', fontWeight: 600 }}>
          {weekOffset === 0 ? 'This week' : `+${weekOffset} week${weekOffset > 1 ? 's' : ''}`}
        </span>
        <button
          onClick={() => setWeekOffset((w) => w + 1)}
          style={{
            width: '26px', height: '26px', borderRadius: '7px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(149,145,244,0.1)',
            border: '1px solid rgba(149,145,244,0.2)',
            cursor: 'pointer', color: '#9591F4',
          }}
        >
          <ChevronRight size={14} />
        </button>
      </div>

      {/* Slot grid */}
      <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {dates.length === 0 ? (
          <p style={{ fontSize: '12px', color: '#C0CAC7', textAlign: 'center', padding: '12px 0' }}>
            No available slots. Try next week →
          </p>
        ) : (
          dates.map((date) => (
            <div key={date}>
              <div style={{ fontSize: '10px', fontWeight: 700, color: '#9591F4', marginBottom: '6px', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
                {date}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '5px' }}>
                {byDate[date].map((slot) => {
                  const time = new Date(slot.start).toLocaleTimeString('en-IN', {
                    hour: '2-digit', minute: '2-digit', hour12: true,
                  });
                  const isSelected = selectedSlot?.start === slot.start;
                  return (
                    <button
                      key={slot.start}
                      onClick={() => setSelectedSlot(isSelected ? null : slot)}
                      className={`slot-btn${isSelected ? ' selected' : ''}`}
                    >
                      {time}
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Confirm booking */}
      {selectedSlot && (
        <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid rgba(149,145,244,0.15)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
            <Clock size={12} color="#9591F4" />
            <span style={{ fontSize: '11px', color: '#DBD7FA', fontWeight: 600 }}>
              {new Date(selectedSlot.start).toLocaleString('en-IN', {
                weekday: 'short', month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit', hour12: true,
              })}
            </span>
          </div>
          <button
            onClick={handleBook}
            disabled={state === 'confirming'}
            style={{
              width: '100%',
              padding: '9px',
              borderRadius: '10px',
              background: state === 'confirming'
                ? 'rgba(90,91,189,0.4)'
                : 'linear-gradient(135deg, #FAD800, #e8c500)',
              color: '#00183D',
              border: 'none',
              fontWeight: 700,
              fontSize: '13px',
              cursor: state === 'confirming' ? 'default' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            {state === 'confirming' ? (
              <>
                <div style={{ width: '14px', height: '14px', border: '2px solid rgba(0,24,61,0.4)', borderTopColor: '#00183D', borderRadius: '50%' }} className="animate-spin" />
                Booking…
              </>
            ) : (
              'Confirm Booking'
            )}
          </button>
        </div>
      )}
    </CardShell>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   ESCROW / COMMITMENT STAKING CARD
══════════════════════════════════════════════════════════════════════ */
type EscrowMethod = 'stripe' | 'usdc';
type EscrowState = 'picking' | 'processing' | 'done' | 'error';

const STAKE_AMOUNTS = [5, 10, 25, 50];

function EscrowCard({
  sessionId,
  leadId,
  apiBase,
}: {
  sessionId: string;
  leadId: string | null;
  apiBase: string;
}) {
  const [method, setMethod] = useState<EscrowMethod>('stripe');
  const [amount, setAmount] = useState(10);
  const [state, setState] = useState<EscrowState>('picking');
  const [errorMsg, setErrorMsg] = useState('');
  const [intentUrl, setIntentUrl] = useState('');

  const handleCommit = async () => {
    setState('processing');
    try {
      const payload: EscrowPayload = {
        type: method,
        amount,
        session_id: sessionId,
        lead_id: leadId ?? 'anonymous',
      };
      const res = await fetch(`${apiBase}/api/v1/escrow/initialize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to initialize escrow');
      const data = await res.json();
      setIntentUrl(data.checkout_url ?? data.tx_url ?? '#');
      setState('done');
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'Unknown error');
      setState('error');
    }
  };

  if (state === 'done') {
    return (
      <CardShell title="Commitment Staked!" icon={<CheckCircle size={14} color="#22C55E" />}>
        <div style={{ textAlign: 'center', padding: '8px 0' }}>
          <div style={{ fontSize: '28px', marginBottom: '8px' }}>🔒</div>
          <p style={{ fontSize: '12px', color: '#DBD7FA', marginBottom: '10px', lineHeight: '1.5' }}>
            ${amount} hold placed via {method === 'stripe' ? 'Stripe' : 'USDC on Base'}.{' '}
            <strong style={{ color: '#22C55E' }}>Fully refundable</strong> if you attend.
          </p>
          {intentUrl && intentUrl !== '#' && (
            <a
              href={intentUrl}
              target="_blank"
              rel="noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '7px 14px',
                borderRadius: '8px',
                background: 'rgba(34,197,94,0.15)',
                border: '1px solid rgba(34,197,94,0.3)',
                color: '#22C55E',
                fontSize: '12px',
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              View Transaction →
            </a>
          )}
        </div>
      </CardShell>
    );
  }

  return (
    <CardShell title="Commitment Stake" icon={<Shield size={14} color="#FAD800" />}>
      {/* Method toggle */}
      <div className="toggle-group" style={{ marginBottom: '12px' }}>
        <button
          className={`toggle-btn${method === 'stripe' ? ' active' : ''}`}
          onClick={() => setMethod('stripe')}
        >
          💳 Stripe (Web2)
        </button>
        <button
          className={`toggle-btn${method === 'usdc' ? ' active' : ''}`}
          onClick={() => setMethod('usdc')}
        >
          ◎ USDC (Web3)
        </button>
      </div>

      {/* Amount selector */}
      <div style={{ marginBottom: '10px' }}>
        <div style={{ fontSize: '10px', fontWeight: 700, color: '#9591F4', marginBottom: '6px', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
          Stake Amount
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '5px' }}>
          {STAKE_AMOUNTS.map((amt) => (
            <button
              key={amt}
              onClick={() => setAmount(amt)}
              className={`slot-btn${amount === amt ? ' selected' : ''}`}
            >
              ${amt}
            </button>
          ))}
        </div>
      </div>

      {/* Disclosure */}
      <div
        style={{
          background: 'rgba(250,216,0,0.06)',
          border: '1px solid rgba(250,216,0,0.2)',
          borderRadius: '8px',
          padding: '8px 10px',
          marginBottom: '10px',
        }}
      >
        <div style={{ display: 'flex', gap: '6px' }}>
          <Zap size={12} color="#FAD800" style={{ flexShrink: 0, marginTop: '1px' }} />
          <p style={{ fontSize: '10px', color: 'rgba(250,216,0,0.85)', lineHeight: '1.6' }}>
            <strong>Attendance Commitment:</strong> Your ${amount} is fully refunded
            within 10 minutes of joining. No-shows forfeit the stake.
            {method === 'usdc' && ' USDC held on Base/Polygon.'}
          </p>
        </div>
      </div>

      {state === 'error' && (
        <p style={{ fontSize: '11px', color: '#EF4444', marginBottom: '8px', textAlign: 'center' }}>{errorMsg}</p>
      )}

      <button
        onClick={handleCommit}
        disabled={state === 'processing'}
        style={{
          width: '100%',
          padding: '10px',
          borderRadius: '10px',
          background:
            state === 'processing'
              ? 'rgba(90,91,189,0.4)'
              : 'linear-gradient(135deg, #5A5BBD, #9591F4)',
          color: 'white',
          border: 'none',
          fontWeight: 700,
          fontSize: '13px',
          cursor: state === 'processing' ? 'default' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '6px',
          boxShadow: state !== 'processing' ? '0 4px 16px rgba(90,91,189,0.35)' : 'none',
        }}
      >
        {state === 'processing' ? (
          <>
            <div style={{ width: '14px', height: '14px', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white', borderRadius: '50%' }} className="animate-spin" />
            Processing…
          </>
        ) : (
          <>
            <Shield size={14} />
            Stake ${amount} {method === 'stripe' ? 'via Stripe' : 'in USDC'}
          </>
        )}
      </button>
    </CardShell>
  );
}

/* ── Shared card shell ────────────────────────────────────────────── */
function CardShell({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: 'linear-gradient(145deg, rgba(21,42,80,0.9) 0%, rgba(10,24,56,0.95) 100%)',
        border: '1px solid rgba(149,145,244,0.25)',
        borderRadius: '14px',
        padding: '14px',
        width: '100%',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          marginBottom: '12px',
          paddingBottom: '10px',
          borderBottom: '1px solid rgba(149,145,244,0.12)',
        }}
      >
        <span style={{ color: '#9591F4' }}>{icon}</span>
        <span style={{ fontSize: '12px', fontWeight: 700, color: '#DBD7FA', letterSpacing: '0.2px' }}>
          {title}
        </span>
      </div>
      {children}
    </div>
  );
}

/* ── Demo slot generator for dev mode ─────────────────────────────── */
function generateDemoSlots(): TimeSlot[] {
  const slots: TimeSlot[] = [];
  const now = new Date();
  for (let d = 1; d <= 5; d++) {
    for (const h of [9, 11, 14, 16]) {
      const start = new Date(now);
      start.setDate(now.getDate() + d);
      start.setHours(h, 0, 0, 0);
      const end = new Date(start);
      end.setMinutes(30);
      if (d === 1 && h < now.getHours() + 2) continue; // Skip past slots today
      slots.push({ start: start.toISOString(), end: end.toISOString(), available: true });
    }
  }
  return slots;
}
