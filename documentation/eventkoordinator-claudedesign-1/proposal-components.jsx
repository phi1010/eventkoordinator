// ─── Mock Data ────────────────────────────────────────────────────────────────
const CURRENT_USER = { id: 'u1', name: 'Max Mustermann', email: 'max@zam-haus.de' }

const CALLS = [
  {
    id: 'c1',
    title: 'Trimesterprogramm Herbst 2026',
    description: 'Einreichungen für Workshops, Vorträge und offene Angebote im Trimester Oktober–Dezember 2026. Alle ZAM-Mitglieder und Freunde des Hauses sind herzlich eingeladen.',
    deadline: new Date('2026-06-15T23:59:00'),
    executionPeriod: 'Oktober – Dezember 2026',
    responsible: 'ZAM Programm-Team',
    types: ['Workshop', 'Vortrag', 'Offenes Angebot'],
  },
  {
    id: 'c2',
    title: 'Sonder-Call: Maschinenkurse',
    description: 'Grundlagenkurse für Maschinen (Lasercutter, 3D-Drucker, CNC) für neue Mitglieder. Diese Kurse sind als Pflichteinweisung konzipiert und laufen fortlaufend.',
    deadline: new Date('2026-05-31T23:59:00'),
    executionPeriod: 'Laufend ab Juni 2026',
    responsible: 'Maschinenteam',
    types: ['Grundlagenkurs'],
  },
]

const MOCK_PROPOSALS = [
  {
    id: 'p1',
    title: 'Einführung Lasercutter',
    submission_type: 'Grundlagenkurs',
    status: 'draft',
    callId: 'c2',
    lastModified: new Date(Date.now() - 1 * 24 * 3600 * 1000),
    area: 'Lasercutter',
    language: 'de',
    abstract: 'Dieser Kurs führt in die sichere Bedienung des Lasercutters ein. Teilnehmende lernen Software, Materialien und Sicherheitsregeln.',
    description: 'Der Kurs umfasst eine theoretische Einführung in die Lasercutter-Software (LightBurn), Materialauswahl und Schnittparameter sowie praktische Übungen an der Maschine. Am Ende sind Teilnehmende befähigt, den Lasercutter eigenständig zu nutzen.',
    internal_notes: 'Benötigt: Laptop mit LightBurn (Demo-Version), Schutzbrillen sind vorhanden.',
    duration_days: 1,
    duration_per_day: ['03:00'],
    duration_same_each_day: true,
    occurrence_count: 2,
    is_basic_course: true,
    max_participants: 6,
    material_cost_eur: '5.00',
    preferred_dates: 'Samstage im Oktober, bevorzugt 10:00–13:00 Uhr',
    is_regular_member: true,
    has_building_access: true,
    editors: [],
    speakers: [
      { id: 's1', display_name: 'Max Mustermann', email: 'max@zam-haus.de', biography: 'Ich bin seit 3 Jahren Mitglied bei ZAM und nutze den Lasercutter regelmäßig für eigene Projekte. Bereits 2 Einführungskurse gehalten.', isCurrentUser: true },
    ],
  },
  {
    id: 'p2',
    title: 'Python für Anfänger',
    submission_type: 'Workshop',
    status: 'submitted',
    callId: 'c1',
    lastModified: new Date(Date.now() - 8 * 24 * 3600 * 1000),
    area: 'Programmierung',
    language: 'de',
    abstract: 'Ein praxisnaher Einstieg in Python. Keine Vorkenntnisse nötig – am Ende schreibt jeder sein erstes Programm.',
    description: 'Wir lernen Python von Grund auf: Variablen, Schleifen, Funktionen und einfache Datenstrukturen. Alle Teilnehmenden schreiben am Ende ein kleines Programm. Ein eigener Laptop ist empfehlenswert.',
    internal_notes: '',
    duration_days: 2,
    duration_per_day: ['04:00', '04:00'],
    duration_same_each_day: true,
    occurrence_count: 1,
    is_basic_course: false,
    max_participants: 12,
    material_cost_eur: '0.00',
    preferred_dates: 'Wochenende im November, z.B. 7./8. oder 14./15. November',
    is_regular_member: false,
    has_building_access: true,
    editors: [{ id: 'u2', email: 'lisa@zam-haus.de', name: 'Lisa Schmidt' }],
    speakers: [
      { id: 's2', display_name: 'Max Mustermann', email: 'max@zam-haus.de', biography: 'Softwareentwickler mit 5 Jahren Python-Erfahrung. Gibt seit 2 Jahren Kurse bei ZAM.', isCurrentUser: true },
      { id: 's3', display_name: 'Lisa Schmidt', email: 'lisa@zam-haus.de', biography: 'Data-Science-Enthusiastin, nutzt Python täglich für Analysen und Visualisierungen.', isCurrentUser: false },
    ],
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────
function daysUntil(date) {
  return Math.max(0, Math.ceil((date - new Date()) / (1000 * 3600 * 24)))
}
function formatDate(date) {
  return date.toLocaleDateString('de-DE', { day: 'numeric', month: 'long', year: 'numeric' })
}
function formatRelative(date) {
  const d = Math.floor((Date.now() - date.getTime()) / (1000 * 3600 * 24))
  if (d === 0) return 'heute'
  if (d === 1) return 'gestern'
  return `vor ${d} Tagen`
}

const STATUS_MAP = {
  draft:         { label: 'Entwurf',       color: '#b45309', bg: '#fef3c7' },
  submitted:     { label: 'Eingereicht',   color: '#1d4ed8', bg: '#dbeafe' },
  accepted:      { label: 'Angenommen',    color: '#166534', bg: '#dcfce7' },
  rejected:      { label: 'Abgelehnt',     color: '#991b1b', bg: '#fee2e2' },
  needs_revision:{ label: 'Überarbeitung', color: '#6d28d9', bg: '#ede9fe' },
}

// ─── Checklist ────────────────────────────────────────────────────────────────
function computeChecklist(d) {
  if (!d) return []
  const mins = (d.duration_per_day || []).reduce((s, t) => {
    const [h, m] = (t || '00:00').split(':').map(Number)
    return s + h * 60 + m
  }, 0)
  return [
    { key: 'title',    label: 'Titel (mind. 3 Zeichen)',                         ok: (d.title || '').length >= 3 },
    { key: 'type',     label: 'Angebotstyp ausgewählt',                          ok: !!d.submission_type },
    { key: 'abstract', label: 'Kurzbeschreibung (50–250 Zeichen)',               ok: (d.abstract||'').length >= 50 && (d.abstract||'').length <= 250 },
    { key: 'desc',     label: 'Ausführliche Beschreibung (mind. 50 Zeichen)',    ok: (d.description||'').length >= 50 },
    { key: 'dur',      label: 'Anzahl der Tage & Dauer pro Tag angegeben',       ok: (d.duration_days||0) >= 1 && mins > 0 },
    { key: 'dates',    label: 'Wunschtermine angegeben',                         ok: (d.preferred_dates||'').trim().length > 5 },
    { key: 'spk',      label: 'Mindestens eine Referent:in eingetragen',         ok: (d.speakers||[]).length >= 1 },
    { key: 'bio',      label: 'Biografie der Referent:innen (mind. 50 Zeichen)', ok: (d.speakers||[]).length > 0 && (d.speakers||[]).every(s => (s.biography||'').length >= 50) },
  ]
}

// ─── Primitive UI Components ──────────────────────────────────────────────────
function StatusBadge({ status }) {
  const { label, color, bg } = STATUS_MAP[status] || STATUS_MAP.draft
  return (
    <span style={{ display:'inline-flex', alignItems:'center', background:bg, color, borderRadius:999, padding:'2px 10px', fontSize:12, fontWeight:600 }}>
      {label}
    </span>
  )
}

function Btn({ children, variant='primary', onClick, disabled, small, full }) {
  const v = {
    primary: { bg:'#646cff', fg:'#fff', hov:'#5259e6' },
    success: { bg:'#4caf50', fg:'#fff', hov:'#3d9443' },
    ghost:   { bg:'transparent', fg:'#646cff', hov:'#eeeeff', border:'1.5px solid #646cff' },
    danger:  { bg:'#fff', fg:'#dc2626', hov:'#fee2e2', border:'1.5px solid #dc2626' },
    muted:   { bg:'#f3f4f6', fg:'#374151', hov:'#e5e7eb' },
    navy:    { bg:'#2c3e50', fg:'#fff', hov:'#243342' },
  }[variant]
  const [hov, setHov] = React.useState(false)
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ padding: small ? '5px 12px' : '9px 18px', background: disabled ? '#e5e7eb' : hov ? v.hov : v.bg,
        color: disabled ? '#9ca3af' : v.fg, border: v.border || 'none', borderRadius:6,
        fontSize: small ? 13 : 14, fontWeight:600, cursor: disabled ? 'not-allowed' : 'pointer',
        transition:'all 150ms', fontFamily:'inherit', whiteSpace:'nowrap',
        width: full ? '100%' : undefined }}>
      {children}
    </button>
  )
}

function FInput({ value, onChange, disabled, placeholder, type='text', maxLength, style }) {
  const [foc, setFoc] = React.useState(false)
  return (
    <input type={type} value={value} onChange={e => onChange(e.target.value)} disabled={disabled}
      placeholder={placeholder} maxLength={maxLength}
      onFocus={() => setFoc(true)} onBlur={() => setFoc(false)}
      style={{ padding:'8px 12px', border:`1.5px solid ${foc ? '#646cff' : '#d1d5db'}`,
        borderRadius:6, fontSize:14, fontFamily:'inherit', width:'100%', outline:'none',
        background: disabled ? '#f9fafb' : '#fff', color:'#111827',
        transition:'border-color 150ms', cursor: disabled ? 'not-allowed' : 'auto', ...style }} />
  )
}

function FTextarea({ value, onChange, disabled, rows=4, placeholder, maxLength }) {
  const [foc, setFoc] = React.useState(false)
  return (
    <textarea value={value} onChange={e => onChange(e.target.value)} disabled={disabled}
      rows={rows} placeholder={placeholder} maxLength={maxLength}
      onFocus={() => setFoc(true)} onBlur={() => setFoc(false)}
      style={{ padding:'8px 12px', border:`1.5px solid ${foc ? '#646cff' : '#d1d5db'}`,
        borderRadius:6, fontSize:14, fontFamily:'inherit', width:'100%', outline:'none', resize:'vertical',
        background: disabled ? '#f9fafb' : '#fff', color:'#111827', transition:'border-color 150ms', minHeight:80 }} />
  )
}

function FSelect({ value, onChange, disabled, children }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} disabled={disabled}
      style={{ padding:'8px 12px', border:'1.5px solid #d1d5db', borderRadius:6, fontSize:14,
        fontFamily:'inherit', width:'100%', outline:'none', background: disabled ? '#f9fafb' : '#fff', color:'#111827' }}>
      {children}
    </select>
  )
}

function Field({ label, hint, required, changed, children }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
      {label && (
        <label style={{ fontSize:13, fontWeight:600, color:'#374151', display:'flex', alignItems:'center', gap:6 }}>
          {label}
          {required && <span style={{ color:'#dc2626', fontSize:11 }}>*</span>}
          {changed && <span title="Ungespeicherte Änderung" style={{ width:6, height:6, borderRadius:'50%', background:'#f59e0b', flexShrink:0, display:'inline-block' }} />}
        </label>
      )}
      {hint && <p style={{ fontSize:12, color:'#6b7280', margin:0, lineHeight:1.4, textWrap:'pretty' }}>{hint}</p>}
      {children}
    </div>
  )
}

function FormSection({ title, children, badge, defaultOpen=true }) {
  const [open, setOpen] = React.useState(defaultOpen)
  return (
    <div style={{ border:'1px solid #e5e7eb', borderRadius:8, overflow:'hidden', background:'#fff' }}>
      <button type="button" onClick={() => setOpen(o => !o)}
        style={{ width:'100%', display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'13px 20px', background: open ? '#fafafa' : '#fff',
          border:'none', borderBottom: open ? '1px solid #e5e7eb' : 'none',
          cursor:'pointer', fontFamily:'inherit' }}>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:14, fontWeight:700, color:'#111827' }}>{title}</span>
          {badge && <span style={{ fontSize:11, background:'#fef3c7', color:'#92400e', borderRadius:999, padding:'2px 8px', fontWeight:600 }}>{badge}</span>}
        </div>
        <span style={{ color:'#9ca3af', fontSize:11, transform: open ? 'rotate(180deg)' : 'none', transition:'transform 200ms', display:'inline-block' }}>▼</span>
      </button>
      {open && <div style={{ padding:'20px', display:'flex', flexDirection:'column', gap:18 }}>{children}</div>}
    </div>
  )
}

// ─── Duration Per Day ─────────────────────────────────────────────────────────
function DurationPerDay({ days, values, sameEachDay, onValuesChange, onSameChange, disabled }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      {days > 1 && (
        <div style={{ display:'flex', gap:20 }}>
          {[true, false].map(opt => (
            <label key={String(opt)} style={{ display:'flex', alignItems:'center', gap:6, fontSize:13, cursor:'pointer', color:'#374151' }}>
              <input type="radio" checked={sameEachDay === opt} onChange={() => onSameChange(opt)} disabled={disabled} />
              {opt ? 'Gleich für alle Tage' : 'Unterschiedlich pro Tag'}
            </label>
          ))}
        </div>
      )}
      {(sameEachDay || days === 1) ? (
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <FInput value={values[0]||''} onChange={v => onValuesChange(Array(days).fill(v.replace(/[^\d:]/g,'')))}
            disabled={disabled} placeholder="HH:MM" style={{ width:110 }} />
          <span style={{ fontSize:13, color:'#6b7280' }}>Std:Min pro Tag</span>
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {Array.from({ length: days }, (_, i) => (
            <div key={i} style={{ display:'flex', alignItems:'center', gap:12 }}>
              <span style={{ fontSize:13, color:'#6b7280', width:48, flexShrink:0 }}>Tag {i+1}</span>
              <FInput value={values[i]||''} onChange={v => { const n=[...values]; n[i]=v.replace(/[^\d:]/g,''); onValuesChange(n) }}
                disabled={disabled} placeholder="HH:MM" style={{ width:110 }} />
              <span style={{ fontSize:12, color:'#9ca3af' }}>Std:Min</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Speaker Card ─────────────────────────────────────────────────────────────
function SpeakerCard({ speaker, onRemove, disabled }) {
  const initials = (speaker.display_name || speaker.email || '?').charAt(0).toUpperCase()
  return (
    <div style={{ display:'flex', gap:12, alignItems:'flex-start', padding:14,
      background:'#fafafa', border:'1px solid #e5e7eb', borderRadius:8 }}>
      <div style={{ width:38, height:38, borderRadius:'50%', background:'#646cff', flexShrink:0,
        display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:700, fontSize:15 }}>
        {initials}
      </div>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontWeight:600, fontSize:14, color:'#111827' }}>{speaker.display_name || speaker.email}</div>
        <div style={{ fontSize:12, color:'#6b7280' }}>{speaker.email}</div>
        {speaker.biography && (
          <div style={{ fontSize:13, color:'#4b5563', marginTop:4, lineHeight:1.5, textWrap:'pretty' }}>
            {speaker.biography.length > 100 ? speaker.biography.slice(0,100)+'…' : speaker.biography}
          </div>
        )}
        {speaker.isCurrentUser && (
          <span style={{ fontSize:11, background:'#eef2ff', color:'#4338ca', borderRadius:999, padding:'2px 8px', fontWeight:600, marginTop:4, display:'inline-block' }}>Ich</span>
        )}
      </div>
      {!disabled && (
        <Btn variant="danger" small onClick={() => onRemove(speaker.id)}>Entfernen</Btn>
      )}
    </div>
  )
}

// ─── Add Speaker Form ─────────────────────────────────────────────────────────
function AddSpeakerInline({ onAdd }) {
  const [f, setF] = React.useState({ email:'', display_name:'', biography:'' })
  const ok = f.email.trim().length > 0
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <Field label="E-Mail-Adresse *">
          <FInput value={f.email} onChange={v => setF(p=>({...p,email:v}))} placeholder="person@beispiel.de" type="email" />
        </Field>
        <Field label="Anzeigename">
          <FInput value={f.display_name} onChange={v => setF(p=>({...p,display_name:v}))} placeholder="Max Mustermann" />
        </Field>
      </div>
      <Field label="Biografie" hint="Wird auf der Website veröffentlicht. Mind. 50 Zeichen empfohlen.">
        <FTextarea value={f.biography} onChange={v => setF(p=>({...p,biography:v}))} rows={2}
          placeholder="Kurze Vorstellung der Person für die Website…" />
        <small style={{ fontSize:11, color: f.biography.length < 50 ? '#f59e0b' : '#9ca3af' }}>
          {f.biography.length} Zeichen{f.biography.length < 50 ? ` (noch ${50-f.biography.length} bis Mindestlänge)` : ' ✓'}
        </small>
      </Field>
      <Btn variant="success" small onClick={() => { if (ok) { onAdd({...f, id:'new-'+Date.now(), isCurrentUser: f.email===CURRENT_USER.email}); setF({email:'',display_name:'',biography:''}) } }} disabled={!ok}>
        + Referent:in hinzufügen
      </Btn>
    </div>
  )
}

// ─── Editor Invite ────────────────────────────────────────────────────────────
function EditorInvite({ editors, onAdd, onRemove, disabled }) {
  const [email, setEmail] = React.useState('')
  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      <div style={{ display:'flex', gap:8 }}>
        <FInput value={email} onChange={setEmail} type="email" placeholder="E-Mail-Adresse eingeben…"
          disabled={disabled} style={{ flex:1 }} />
        <Btn variant="ghost" disabled={disabled||!valid} onClick={() => { onAdd(email); setEmail('') }}>
          Einladen
        </Btn>
      </div>
      {editors.length > 0 && (
        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
          {editors.map(e => (
            <span key={e.id||e.email} style={{ display:'inline-flex', alignItems:'center', gap:4,
              background:'#eef2ff', color:'#4338ca', borderRadius:999, padding:'4px 10px', fontSize:13, fontWeight:500 }}>
              {e.email||e.name}
              {!disabled && <button type="button" onClick={() => onRemove(e.id||e.email)}
                style={{ background:'none', border:'none', color:'#4338ca', cursor:'pointer', padding:'0 0 0 2px', fontSize:15, lineHeight:1 }}>×</button>}
            </span>
          ))}
        </div>
      )}
      <p style={{ fontSize:12, color:'#6b7280', margin:0 }}>
        Eingeladene Personen erhalten einen Link per E-Mail. Sie müssen noch keinen Account haben.
      </p>
    </div>
  )
}

// ─── Checklist Panel ──────────────────────────────────────────────────────────
function ChecklistPanel({ formData }) {
  const items = computeChecklist(formData)
  const done = items.filter(i => i.ok).length
  const allOk = done === items.length
  return (
    <div style={{ background:'#fff', border:'1px solid #e5e7eb', borderRadius:8, overflow:'hidden' }}>
      <div style={{ padding:'13px 16px', background:'#fafafa', borderBottom:'1px solid #e5e7eb',
        display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <span style={{ fontSize:13, fontWeight:700, color:'#111827' }}>Einreichungs-Checkliste</span>
        <span style={{ fontSize:12, fontWeight:600, color: allOk ? '#166534' : '#6b7280' }}>
          {done}/{items.length}{allOk ? ' ✓ Bereit!' : ''}
        </span>
      </div>
      <div style={{ padding:'12px 16px', display:'flex', flexDirection:'column', gap:7 }}>
        {items.map(({ key, label, ok }) => (
          <div key={key} style={{ display:'flex', gap:8, alignItems:'flex-start' }}>
            <span style={{ fontSize:14, lineHeight:'19px', flexShrink:0, color: ok ? '#16a34a' : '#d1d5db', fontWeight:700 }}>
              {ok ? '✓' : '○'}
            </span>
            <span style={{ fontSize:13, color: ok ? '#374151' : '#9ca3af', lineHeight:1.45, textWrap:'pretty' }}>{label}</span>
          </div>
        ))}
        {!allOk && (
          <p style={{ fontSize:12, color:'#6b7280', margin:'4px 0 0 0', paddingTop:8, borderTop:'1px solid #f3f4f6', textWrap:'pretty' }}>
            Alle Punkte müssen erfüllt sein, um den Vorschlag einzureichen.
          </p>
        )}
      </div>
    </div>
  )
}

Object.assign(window, {
  CURRENT_USER, CALLS, MOCK_PROPOSALS,
  daysUntil, formatDate, formatRelative, STATUS_MAP,
  computeChecklist,
  StatusBadge, Btn, FInput, FTextarea, FSelect, Field, FormSection,
  DurationPerDay, SpeakerCard, AddSpeakerInline, EditorInvite, ChecklistPanel,
})
