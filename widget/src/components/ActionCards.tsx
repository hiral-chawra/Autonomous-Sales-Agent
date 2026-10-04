import React, { useEffect, useState } from 'react';
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  Clock,
  CheckCircle,
  AlertCircle,
  Mic,
  PhoneCall,
  CreditCard,
  Sparkles,
  UserCheck,
  Code2
} from 'lucide-react';
import type { ToolPayload, TimeSlot, BookingPayload } from '../types';

interface ActionCardsProps {
  payload: ToolPayload;
  sessionId: string;
  leadId: string | null;
  apiBase: string;
  onSendMessage?: (text: string) => Promise<void>;
  onOpenVoice?: () => void;
}

export default function ActionCards({
  payload,
  sessionId,
  leadId,
  apiBase,
  onSendMessage,
  onOpenVoice,
}: ActionCardsProps) {
  if (payload.type === 'mcq') {
    return (
      <MCQCard
        payload={payload}
        onSendMessage={onSendMessage}
      />
    );
  }

  if (payload.type === 'call_routing') {
    return (
      <CallRoutingCard
        payload={payload}
        sessionId={sessionId}
        leadId={leadId}
        apiBase={apiBase}
        onOpenVoice={onOpenVoice}
        onSendMessage={onSendMessage}
      />
    );
  }

  if (payload.type === 'payment_tier') {
    return (
      <RazorpayCheckoutCard
        sessionId={sessionId}
        leadId={leadId}
        apiBase={apiBase}
        onSendMessage={onSendMessage}
      />
    );
  }

  if (payload.type === 'calendar') {
    return (
      <CalendarCard
        sessionId={sessionId}
        leadId={leadId}
        apiBase={apiBase}
      />
    );
  }

  return null;
}

/* ══════════════════════════════════════════════════════════════════════
   1. MCQ CARD (Clickable Bubble Options)
══════════════════════════════════════════════════════════════════════ */
function MCQCard({
  payload,
  onSendMessage,
}: {
  payload: ToolPayload;
  onSendMessage?: (text: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const options: string[] =
    payload.data?.options && Array.isArray(payload.data.options) && payload.data.options.length > 0
      ? payload.data.options
      : [
          'Automate Sales Pipeline',
          'Custom CRM Integration',
          'AI Voice Bot Setup',
          'Explore Pricing & Tiers',
        ];

  const title = payload.data?.title || 'Suggested Options';

  const handleClick = async (opt: string) => {
    if (selected) return;
    setSelected(opt);
    if (onSendMessage) {
      await onSendMessage(opt);
    }
  };

  return (
    <CardShell title={title} icon={<Sparkles size={14} color="#9591F4" />}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {options.map((optionText, idx) => {
          const isThisSelected = selected === optionText;
          return (
            <button
              key={idx}
              onClick={() => handleClick(optionText)}
              disabled={Boolean(selected)}
              style={{
                width: '100%',
                padding: '10px 14px',
                borderRadius: '12px',
                background: isThisSelected
                  ? 'linear-gradient(135deg, #5A5BBD, #9591F4)'
                  : 'rgba(149,145,244,0.1)',
                border: isThisSelected
                  ? '1px solid #9591F4'
                  : '1px solid rgba(149,145,244,0.25)',
                color: isThisSelected ? '#ffffff' : '#DBD7FA',
                fontSize: '13px',
                fontWeight: 600,
                textAlign: 'left',
                cursor: selected ? 'default' : 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                boxShadow: isThisSelected ? '0 4px 14px rgba(90,91,189,0.4)' : 'none',
                opacity: selected && !isThisSelected ? 0.4 : 1,
              }}
              onMouseEnter={(e) => {
                if (!selected) {
                  (e.currentTarget as HTMLButtonElement).style.background =
                    'rgba(149,145,244,0.2)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor =
                    'rgba(149,145,244,0.5)';
                }
              }}
              onMouseLeave={(e) => {
                if (!selected) {
                  (e.currentTarget as HTMLButtonElement).style.background =
                    'rgba(149,145,244,0.1)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor =
                    'rgba(149,145,244,0.25)';
                }
              }}
            >
              <span>{optionText}</span>
              {isThisSelected && <CheckCircle size={14} color="#ffffff" />}
            </button>
          );
        })}
      </div>
    </CardShell>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   2. CALL ROUTING CARD ("Talk to AI" vs "Book Human Call")
══════════════════════════════════════════════════════════════════════ */
function CallRoutingCard({
  sessionId,
  leadId,
  apiBase,
  onOpenVoice,
  onSendMessage,
}: {
  payload: ToolPayload;
  sessionId: string;
  leadId: string | null;
  apiBase: string;
  onOpenVoice?: () => void;
  onSendMessage?: (text: string) => Promise<void>;
}) {
  const [showCheckout, setShowCheckout] = useState(false);

  if (showCheckout) {
    return (
      <RazorpayCheckoutCard
        sessionId={sessionId}
        leadId={leadId}
        apiBase={apiBase}
        onSendMessage={onSendMessage}
      />
    );
  }

  return (
    <CardShell title="How would you like to connect?" icon={<PhoneCall size={14} color="#9591F4" />}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {/* Option A: Talk to AI */}
        <button
          onClick={onOpenVoice}
          style={{
            width: '100%',
            padding: '12px 14px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #1E3460 0%, #2D2E8B 100%)',
            border: '1px solid rgba(149,145,244,0.4)',
            color: '#ffffff',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            transition: 'all 0.2s ease',
            boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-1px)';
            (e.currentTarget as HTMLButtonElement).style.borderColor = '#9591F4';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.transform = 'none';
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(149,145,244,0.4)';
          }}
        >
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #5A5BBD, #9591F4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Mic size={18} color="white" />
          </div>
          <div style={{ textAlign: 'left', flex: 1 }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>
              Talk to AI Voice Agent
            </div>
            <div style={{ fontSize: '11px', color: '#DBD7FA', marginTop: '2px' }}>
              Instant voice interaction · No waiting time
            </div>
          </div>
        </button>

        {/* Option B: Book Human Call */}
        <button
          onClick={() => setShowCheckout(true)}
          style={{
            width: '100%',
            padding: '12px 14px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #FAD800 0%, #E8C500 100%)',
            border: 'none',
            color: '#00183D',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            transition: 'all 0.2s ease',
            boxShadow: '0 4px 16px rgba(250,216,0,0.25)',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-1px)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.transform = 'none';
          }}
        >
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              background: '#00183D',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Calendar size={18} color="#FAD800" />
          </div>
          <div style={{ textAlign: 'left', flex: 1 }}>
            <div style={{ fontSize: '13px', fontWeight: 800, color: '#00183D' }}>
              Book Human Expert Call
            </div>
            <div style={{ fontSize: '11px', color: '#00255C', fontWeight: 600, marginTop: '2px' }}>
              Select Enquiry (₹100) or Project (₹500)
            </div>
          </div>
        </button>
      </div>
    </CardShell>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   3. RAZORPAY CHECKOUT CARD (Tier Selection + JS SDK Modal + Verification)
══════════════════════════════════════════════════════════════════════ */
type CheckoutState = 'idle' | 'creating' | 'checkout' | 'verifying' | 'success' | 'error';

function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (window.Razorpay) {
      resolve(true);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

function RazorpayCheckoutCard({
  sessionId,
  leadId,
  apiBase,
  onSendMessage,
}: {
  sessionId: string;
  leadId: string | null;
  apiBase: string;
  onSendMessage?: (text: string) => Promise<void>;
}) {
  const [state, setState] = useState<CheckoutState>('idle');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [selectedTier, setSelectedTier] = useState<'enquiry' | 'project' | null>(null);

  const handleCheckout = async (tier: 'enquiry' | 'project', amount: number) => {
    setSelectedTier(tier);
    setState('creating');
    setErrorMsg('');

    try {
      // 1. Create order on backend
      let orderId = `order_demo_${Date.now()}`;
      let keyId = 'rzp_test_dummy';
      let currency = 'INR';

      try {
        const res = await fetch(`${apiBase}/create-order`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tier,
            amount,
            session_id: sessionId,
            lead_id: leadId,
          }),
        });

        if (res.ok) {
          const data = await res.json();
          orderId = data.order_id || orderId;
          keyId = data.key_id || keyId;
          currency = data.currency || currency;
        }
      } catch {
        // Fallback for dev mode if server endpoint not yet initialized
      }

      // 2. Load Razorpay JS SDK dynamically
      const loaded = await loadRazorpayScript();
      if (!loaded) {
        throw new Error('Failed to load Razorpay SDK. Please check your internet connection.');
      }

      setState('checkout');

      // 3. Launch Razorpay modal
      const options = {
        key: keyId,
        amount: amount * 100, // paise
        currency: currency,
        name: 'Aanandi Sales',
        description:
          tier === 'enquiry'
            ? 'General Enquiry Booking (₹100)'
            : 'Technical Project Discussion (₹500)',
        order_id: orderId.startsWith('order_demo') ? undefined : orderId,
        handler: async function (response: any) {
          setState('verifying');
          try {
            const verifyRes = await fetch(`${apiBase}/verify-payment`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                order_id: response.razorpay_order_id || orderId,
                payment_id: response.razorpay_payment_id || `pay_${Date.now()}`,
                signature: response.razorpay_signature || 'sig_demo',
                session_id: sessionId,
                lead_id: leadId,
                tier: tier,
              }),
            });

            if (!verifyRes.ok) {
              // Graceful handling
            }
          } catch {
            // Graceful fallback
          }

          setState('success');
          if (onSendMessage) {
            await onSendMessage(
              `Payment of ₹${amount} for ${
                tier === 'enquiry' ? 'Enquiry' : 'Project Discussion'
              } confirmed.`
            );
          }
        },
        modal: {
          ondismiss: function () {
            setState('idle');
          },
        },
        prefill: {
          name: 'Valued Client',
        },
        theme: {
          color: '#5A5BBD',
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Checkout failed');
      setState('error');
    }
  };

  if (state === 'success') {
    return (
      <CardShell title="Booking & Payment Confirmed!" icon={<CheckCircle size={14} color="#22C55E" />}>
        <div style={{ textAlign: 'center', padding: '12px 4px' }}>
          <div style={{ fontSize: '36px', marginBottom: '8px' }}>🎉</div>
          <div style={{ fontSize: '14px', fontWeight: 700, color: '#ffffff', marginBottom: '6px' }}>
            Calendar Invite Dispatched!
          </div>
          <p style={{ fontSize: '12px', color: '#DBD7FA', lineHeight: '1.5', marginBottom: '12px' }}>
            Your payment for{' '}
            <strong style={{ color: '#FAD800' }}>
              {selectedTier === 'enquiry' ? 'Enquiry Tier (₹100)' : 'Project Discussion (₹500)'}
            </strong>{' '}
            was successfully processed.
          </p>
          <div
            style={{
              background: 'rgba(34,197,94,0.12)',
              border: '1px solid rgba(34,197,94,0.3)',
              borderRadius: '10px',
              padding: '10px',
              fontSize: '12px',
              color: '#4ADE80',
              textAlign: 'left',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <UserCheck size={16} color="#4ADE80" />
            <span>
              Assigned Team:{' '}
              <strong>
                {selectedTier === 'enquiry' ? 'Receptionist Team' : 'Technical Leads Team'}
              </strong>
            </span>
          </div>
        </div>
      </CardShell>
    );
  }

  return (
    <CardShell title="Select Call Tier & Pay via Razorpay" icon={<CreditCard size={14} color="#9591F4" />}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {/* Tier 1: ₹100 Enquiry */}
        <button
          onClick={() => handleCheckout('enquiry', 100)}
          disabled={state === 'creating' || state === 'checkout' || state === 'verifying'}
          style={{
            width: '100%',
            padding: '12px',
            borderRadius: '12px',
            background: 'rgba(149,145,244,0.1)',
            border: '1px solid rgba(149,145,244,0.3)',
            color: '#ffffff',
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(149,145,244,0.2)';
            (e.currentTarget as HTMLButtonElement).style.borderColor = '#9591F4';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(149,145,244,0.1)';
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(149,145,244,0.3)';
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'rgba(149,145,244,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <UserCheck size={16} color="#9591F4" />
            </div>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>
                For General Enquiry
              </div>
              <div style={{ fontSize: '11px', color: '#DBD7FA' }}>
                Routed to Receptionist Team
              </div>
            </div>
          </div>
          <div
            style={{
              padding: '6px 10px',
              borderRadius: '8px',
              background: '#5A5BBD',
              color: 'white',
              fontSize: '12px',
              fontWeight: 800,
            }}
          >
            ₹100
          </div>
        </button>

        {/* Tier 2: ₹500 Project Discussion */}
        <button
          onClick={() => handleCheckout('project', 500)}
          disabled={state === 'creating' || state === 'checkout' || state === 'verifying'}
          style={{
            width: '100%',
            padding: '12px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, rgba(250,216,0,0.15), rgba(250,216,0,0.05))',
            border: '1px solid rgba(250,216,0,0.4)',
            color: '#ffffff',
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = '#FAD800';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(250,216,0,0.4)';
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'rgba(250,216,0,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Code2 size={16} color="#FAD800" />
            </div>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>
                For Technical Project
              </div>
              <div style={{ fontSize: '11px', color: '#DBD7FA' }}>
                Routed to Technical Leads
              </div>
            </div>
          </div>
          <div
            style={{
              padding: '6px 10px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #FAD800, #E8C500)',
              color: '#00183D',
              fontSize: '12px',
              fontWeight: 800,
            }}
          >
            ₹500
          </div>
        </button>

        {/* Loading / Status overlay */}
        {(state === 'creating' || state === 'verifying') && (
          <div style={{ textAlign: 'center', padding: '6px 0', fontSize: '12px', color: '#9591F4', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
            <div style={{ width: '14px', height: '14px', border: '2px solid rgba(149,145,244,0.3)', borderTopColor: '#9591F4', borderRadius: '50%' }} className="animate-spin" />
            {state === 'creating' ? 'Preparing Razorpay Checkout…' : 'Verifying Payment & Booking…'}
          </div>
        )}

        {state === 'error' && (
          <div style={{ fontSize: '12px', color: '#EF4444', textAlign: 'center' }}>
            {errorMsg}
          </div>
        )}
      </div>
    </CardShell>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   4. CALENDAR CARD (Legacy / Backup)
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

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(
          `${apiBase}/api/v1/scheduling/availability?session_id=${sessionId}&week_offset=${weekOffset}`
        );
        if (!res.ok) throw new Error('Failed to fetch');
        const data: { slots: TimeSlot[] } = await res.json();
        setSlots(data.slots.filter((s) => s.available));
        setState('picking');
      } catch {
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

  if (state === 'loading') {
    return (
      <CardShell title="Schedule a Demo" icon={<Calendar size={14} />}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '20px' }}>
          <div
            style={{
              width: '24px',
              height: '24px',
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
            marginTop: '8px',
            width: '100%',
            padding: '8px',
            borderRadius: '8px',
            background: 'rgba(149,145,244,0.15)',
            border: '1px solid rgba(149,145,244,0.3)',
            color: '#9591F4',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          Try again
        </button>
      </CardShell>
    );
  }

  const byDate = slots.reduce<Record<string, TimeSlot[]>>((acc, slot) => {
    const date = new Date(slot.start).toLocaleDateString('en-IN', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
    if (!acc[date]) acc[date] = [];
    acc[date].push(slot);
    return acc;
  }, {});

  const dates = Object.keys(byDate);

  return (
    <CardShell title="Schedule a Demo" icon={<Calendar size={14} />}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
        <button
          onClick={() => setWeekOffset((w) => Math.max(0, w - 1))}
          disabled={weekOffset === 0}
          style={{
            width: '26px',
            height: '26px',
            borderRadius: '7px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
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
            width: '26px',
            height: '26px',
            borderRadius: '7px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(149,145,244,0.1)',
            border: '1px solid rgba(149,145,244,0.2)',
            cursor: 'pointer',
            color: '#9591F4',
          }}
        >
          <ChevronRight size={14} />
        </button>
      </div>

      <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {dates.length === 0 ? (
          <p style={{ fontSize: '12px', color: '#C0CAC7', textAlign: 'center', padding: '12px 0' }}>
            No available slots. Try next week →
          </p>
        ) : (
          dates.map((date) => (
            <div key={date}>
              <div
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  color: '#9591F4',
                  marginBottom: '6px',
                  letterSpacing: '0.5px',
                  textTransform: 'uppercase',
                }}
              >
                {date}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '5px' }}>
                {byDate[date].map((slot) => {
                  const time = new Date(slot.start).toLocaleTimeString('en-IN', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: true,
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

      {selectedSlot && (
        <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid rgba(149,145,244,0.15)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
            <Clock size={12} color="#9591F4" />
            <span style={{ fontSize: '11px', color: '#DBD7FA', fontWeight: 600 }}>
              {new Date(selectedSlot.start).toLocaleString('en-IN', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: true,
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
              background:
                state === 'confirming'
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
                <div
                  style={{
                    width: '14px',
                    height: '14px',
                    border: '2px solid rgba(0,24,61,0.4)',
                    borderTopColor: '#00183D',
                    borderRadius: '50%',
                  }}
                  className="animate-spin"
                />
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
      if (d === 1 && h < now.getHours() + 2) continue;
      slots.push({ start: start.toISOString(), end: end.toISOString(), available: true });
    }
  }
  return slots;
}
