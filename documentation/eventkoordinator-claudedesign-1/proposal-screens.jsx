// ─── Navbar ───────────────────────────────────────────────────────────────────
function Navbar({ screen, onNav }) {
  return (
    <nav style={{ background:'#2c3e50', color:'#fff', padding:'0', boxShadow:'0 2px 8px rgba(0,0,0,0.15)', position:'relative', zIndex:100 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'0.85rem 2rem', gap:'2rem', maxWidth:1400, margin:'0 auto' }}>
        <button type="button" onClick={() => onNav('home')}
          style={{ background:'none', border:'none', color:'#fff', fontSize:'1.35rem', fontWeight:700, cursor:'pointer', fontFamily:'inherit', letterSpacing:'.3px', padding:0 }}>
          Event Coordinator
        </button>
        <div style={{ display:'flex', gap:'0.5rem' }}>
          {[['home','Startseite'],['editor','Meine Vorschläge']].map(([s, label]) => (
            <button key={s} type="button" onClick={() => onNav(s)}
              style={{ background: screen===s ? 'rgba(255,255,255,0.18)' : 'transparent',
                border: screen===s ? '1px solid rgba(255,255,255,0.3)' : '1px solid transparent',
                color:'#fff', padding:'0.35rem 0.7rem', borderRadius:6, fontSize:14, cursor:'pointer', fontFamily:'inherit', transition:'all 150ms' }}>
              {label}
            </button>
          ))}
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8, fontSize:14, color:'rgba(255,255,255,0.8)' }}>
          <div style={{ width:30, height:30, borderRadius:'50%', background:'rgba(255,255,255,0.2)', display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700, fontSize:14 }}>
            {CURRENT_USER.name.charAt(0)}
          </div>
          {CURRENT_USER.name.split(' ')[0]}
        </div>
      </div>
    </nav>
  )
}

// ─── Home Screen ──────────────────────────────────────────────────────────────
function CallCard({ call, myProposals, onSubmit, onEdit }) {
  const days = daysUntil(call.deadline)
  const myProps = myProposals.filter(p => p.callId === call.id)
  const urgent = days <= 7

  return (
    <div style={{ background:'#fff', border:'1px solid #e5e7eb', borderRadius:12, overflow:'hidden',
      boxShadow:'0 1px 4px rgba(0,0,0,0.06)', display:'flex', flexDirection:'column' }}>
      <div style={{ padding:'20px 24px 16px', flex:1 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:12, marginBottom:8 }}>
          <h2 style={{ fontSize:17, fontWeight:700, color:'#111827', margin:0, lineHeight:1.3 }}>{call.title}</h2>
          <span style={{ fontSize:12, fontWeight:700, background: urgent ? '#fee2e2' : '#f0fdf4',
            color: urgent ? '#dc2626' : '#166534', borderRadius:999, padding:'3px 10px', whiteSpace:'nowrap', flexShrink:0 }}>
            {days === 0 ? 'Heute' : `Noch ${days} Tage`}
          </span>
        </div>
        <p style={{ fontSize:14, color:'#4b5563', lineHeight:1.55, margin:'0 0 14px 0', textWrap:'pretty' }}>{call.description}</p>
        <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
          <div style={{ display:'flex', gap:16, fontSize:12, color:'#6b7280' }}>
            <span>📅 Durchführung: <strong style={{ color:'#374151' }}>{call.executionPeriod}</strong></span>
            <span>⏰ Deadline: <strong style={{ color: urgent ? '#dc2626' : '#374151' }}>{formatDate(call.deadline)}</strong></span>
          </div>
          <div style={{ fontSize:12, color:'#6b7280' }}>
            👤 Verantwortlich: <strong style={{ color:'#374151' }}>{call.responsible}</strong>
          </div>
          <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginTop:4 }}>
            {call.types.map(t => (
              <span key={t} style={{ fontSize:11, background:'#f3f4f6', color:'#374151', borderRadius:999, padding:'2px 8px', fontWeight:500 }}>{t}</span>
            ))}
          </div>
        </div>
      </div>

      {myProps.length > 0 && (
        <div style={{ borderTop:'1px solid #f3f4f6', padding:'10px 24px', background:'#fafafa', display:'flex', flexDirection:'column', gap:6 }}>
          <p style={{ fontSize:12, fontWeight:600, color:'#6b7280', margin:0 }}>Meine Einreichungen für diesen Call:</p>
          {myProps.map(p => (
            <div key={p.id} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:8 }}>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <StatusBadge status={p.status} />
                <span style={{ fontSize:13, fontWeight:600, color:'#111827' }}>{p.title}</span>
                <span style={{ fontSize:12, color:'#9ca3af' }}>· {formatRelative(p.lastModified)}</span>
              </div>
              <Btn variant="ghost" small onClick={() => onEdit(p.id)}>Öffnen</Btn>
            </div>
          ))}
        </div>
      )}

      <div style={{ padding:'12px 24px', borderTop:'1px solid #f3f4f6', display:'flex', gap:8 }}>
        <Btn variant="primary" onClick={() => onSubmit(call.id)} full>
          {myProps.length > 0 ? '+ Weiteren Vorschlag einreichen' : 'Vorschlag einreichen'}
        </Btn>
      </div>
    </div>
  )
}

function HomeScreen({ proposals, onNavigateEditor, onNewProposal }) {
  return (
    <div style={{ maxWidth:900, margin:'0 auto', padding:'40px 24px' }}>
      <div style={{ marginBottom:32 }}>
        <h1 style={{ fontSize:26, fontWeight:800, color:'#111827', margin:'0 0 6px 0' }}>Aktuelle Ausschreibungen</h1>
        <p style={{ fontSize:15, color:'#6b7280', margin:0 }}>
          Reiche einen Vorschlag für einen Workshop, Kurs oder Vortrag ein.
        </p>
      </div>

      <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
        {CALLS.map(call => (
          <CallCard key={call.id} call={call} myProposals={proposals}
            onSubmit={() => onNewProposal(call.id)}
            onEdit={id => onNavigateEditor(id)} />
        ))}
      </div>

      {proposals.some(p => !CALLS.find(c => c.id === p.callId)) && (
        <div style={{ marginTop:32 }}>
          <h2 style={{ fontSize:16, fontWeight:700, color:'#374151', marginBottom:12 }}>Weitere Vorschläge</h2>
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {proposals.filter(p => !CALLS.find(c => c.id === p.callId)).map(p => (
              <div key={p.id} style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
                padding:'12px 16px', background:'#fff', border:'1px solid #e5e7eb', borderRadius:8 }}>
                <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                  <StatusBadge status={p.status} />
                  <span style={{ fontWeight:600, color:'#111827' }}>{p.title}</span>
                  <span style={{ fontSize:12, color:'#9ca3af' }}>· {formatRelative(p.lastModified)}</span>
                </div>
                <Btn variant="ghost" small onClick={() => onNavigateEditor(p.id)}>Öffnen</Btn>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Proposal Form ────────────────────────────────────────────────────────────
function ProposalFormContent({ initialData, disabled, layout }) {
  const [data, setData] = React.useState(initialData)
  const [changed, setChanged] = React.useState(new Set())
  const [saved, setSaved] = React.useState(false)
  const [wizardStep, setWizardStep] = React.useState(0)

  const set = (field, value) => {
    setData(p => ({ ...p, [field]: value }))
    setChanged(p => new Set([...p, field]))
    setSaved(false)
  }

  const isDraft = data.status === 'draft'
  const hasChanges = changed.size > 0
  const checklist = computeChecklist(data)
  const allOk = checklist.every(i => i.ok)

  const alreadySpeaker = data.speakers.some(s => s.email === CURRENT_USER.email)

  const handleAddSelf = () => {
    if (!alreadySpeaker) {
      set('speakers', [...data.speakers, {
        id: 'self-' + Date.now(), display_name: CURRENT_USER.name,
        email: CURRENT_USER.email, biography: '', isCurrentUser: true,
      }])
    }
  }

  // ── Warning Banner
  const warningBanner = isDraft && (
    <div style={{ display:'flex', gap:12, padding:'12px 16px', background:'#fef3c7',
      border:'1px solid #fbbf24', borderLeft:'4px solid #f59e0b', borderRadius:8 }}>
      <span style={{ fontSize:17, flexShrink:0 }}>⚠</span>
      <div>
        <p style={{ fontSize:14, fontWeight:700, color:'#92400e', margin:'0 0 2px 0' }}>Entwurf – noch nicht eingereicht</p>
        <p style={{ fontSize:13, color:'#a16207', margin:0, textWrap:'pretty' }}>
          Gespeichert ≠ eingereicht. Dieser Vorschlag wird erst berücksichtigt, nachdem du ihn über „Vorschlag einreichen" abgesendet hast.
        </p>
      </div>
    </div>
  )

  // ── Save bar
  const saveBar = !disabled && (
    <div style={{ display:'flex', gap:10, alignItems:'center', flexWrap:'wrap', padding:'16px 0 0 0', borderTop:'1px solid #e5e7eb' }}>
      <Btn variant="success" onClick={() => { setSaved(true); setChanged(new Set()) }} disabled={!hasChanges}>
        Entwurf speichern
      </Btn>
      {hasChanges && (
        <Btn variant="muted" onClick={() => { setData(initialData); setChanged(new Set()); setSaved(false) }}>
          Verwerfen
        </Btn>
      )}
      {allOk && isDraft && !hasChanges && (
        <Btn variant="primary" onClick={() => alert('Demo: Vorschlag wurde eingereicht!')}>
          Vorschlag einreichen →
        </Btn>
      )}
      {saved && !hasChanges && <span style={{ fontSize:13, color:'#16a34a', fontWeight:500 }}>✓ Gespeichert</span>}
    </div>
  )

  // ── Form sections (shared across layouts)
  const sectionAllgemein = (
    <FormSection title="Allgemeine Informationen" defaultOpen={true}>
      <Field label="Titel" required changed={changed.has('title')} hint="Maximal 30 Zeichen. Kurz, prägnant und einprägsam.">
        <FInput value={data.title} onChange={v => set('title', v.slice(0,30))} disabled={disabled} maxLength={30} />
        <small style={{ fontSize:11, color: data.title.length < 3 ? '#f59e0b' : '#9ca3af' }}>{data.title.length}/30</small>
      </Field>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <Field label="Angebotstyp" required changed={changed.has('submission_type')}
          hint="Workshop: buchungspflichtig, mit Gebühr; Offenes Angebot: keine Buchung nötig">
          <FSelect value={data.submission_type} onChange={v => set('submission_type', v)} disabled={disabled}>
            <option value="">– Bitte wählen –</option>
            <option value="Workshop">Workshop</option>
            <option value="Vortrag">Vortrag</option>
            <option value="Offenes Angebot">Offenes Angebot</option>
            <option value="Grundlagenkurs">Grundlagenkurs (Pflichteinweisung)</option>
          </FSelect>
        </Field>
        <Field label="Sprache" changed={changed.has('language')}>
          <FSelect value={data.language} onChange={v => set('language', v)} disabled={disabled}>
            <option value="">– Bitte wählen –</option>
            <option value="de">Deutsch</option>
            <option value="en">Englisch</option>
            <option value="de/en">Deutsch / Englisch</option>
          </FSelect>
        </Field>
      </div>
      <Field label="Themenbereich" changed={changed.has('area')}>
        <FSelect value={data.area} onChange={v => set('area', v)} disabled={disabled}>
          <option value="">– Kein Themenbereich –</option>
          <option value="Programmierung">Programmierung</option>
          <option value="Elektronik">Elektronik</option>
          <option value="Holz & Metall">Holz & Metall</option>
          <option value="Textil">Textil</option>
          <option value="Lasercutter">Lasercutter</option>
          <option value="3D-Druck">3D-Druck</option>
          <option value="Sonstiges">Sonstiges</option>
        </FSelect>
      </Field>
      <Field label="Kurzbeschreibung" required changed={changed.has('abstract')}
        hint="Wird im Programm-Überblick auf der Website veröffentlicht. (50–250 Zeichen)">
        <FTextarea value={data.abstract} onChange={v => set('abstract', v)} disabled={disabled} rows={3} maxLength={250} />
        <small style={{ fontSize:11, color: (data.abstract.length<50||data.abstract.length>250) ? '#f59e0b' : '#9ca3af' }}>
          {data.abstract.length}/250{data.abstract.length < 50 ? ` · noch ${50-data.abstract.length} Zeichen` : ''}
        </small>
      </Field>
      <Field label="Ausführliche Beschreibung" required changed={changed.has('description')}
        hint="Auf der Detailseite veröffentlicht. Bitte Ziele, Voraussetzungen und was Teilnehmende mitnehmen beschreiben. (50–1000 Zeichen)">
        <FTextarea value={data.description} onChange={v => set('description', v)} disabled={disabled} rows={6} maxLength={1000} />
        <small style={{ fontSize:11, color: data.description.length<50 ? '#f59e0b' : '#9ca3af' }}>{data.description.length}/1000</small>
      </Field>
      <Field label="Interne Hinweise (optional)" changed={changed.has('internal_notes')}
        hint="Nicht öffentlich. Technikbedarf, besondere Anforderungen an Raum oder Ausstattung.">
        <FTextarea value={data.internal_notes} onChange={v => set('internal_notes', v)} disabled={disabled} rows={2} />
      </Field>
    </FormSection>
  )

  const sectionZeitplanung = (
    <FormSection title="Zeitplanung" defaultOpen={true}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <Field label="Anzahl der Tage" required changed={changed.has('duration_days')}
          hint="Wie viele Tage dauert das Angebot insgesamt?">
          <FInput type="number" value={String(data.duration_days)} onChange={v => {
            const d = Math.max(1, parseInt(v)||1)
            set('duration_days', d)
            set('duration_per_day', Array(d).fill(data.duration_per_day[0]||'02:00'))
          }} disabled={disabled} />
        </Field>
        <Field label="Häufigkeit im Call-Zeitraum" required changed={changed.has('occurrence_count')}
          hint="Wie oft wird das Angebot angeboten? Standard: 1. Bei 3-monatigem Call: 3 = monatlich.">
          <FInput type="number" value={String(data.occurrence_count)} onChange={v => set('occurrence_count', Math.max(1, parseInt(v)||1))} disabled={disabled} />
        </Field>
      </div>
      <Field label="Dauer pro Tag" required changed={changed.has('duration_per_day')}
        hint={data.duration_days > 1 ? 'Kannst du pro Tag unterschiedlich eintragen.' : 'Format: HH:MM, z.B. 02:30 für 2,5 Stunden.'}>
        <DurationPerDay days={data.duration_days} values={data.duration_per_day}
          sameEachDay={data.duration_same_each_day}
          onValuesChange={v => set('duration_per_day', v)}
          onSameChange={v => { set('duration_same_each_day', v); if (v) set('duration_per_day', Array(data.duration_days).fill(data.duration_per_day[0]||'02:00')) }}
          disabled={disabled} />
      </Field>
      <Field label="Wunschtermine und Alternativen" required changed={changed.has('preferred_dates')}
        hint="Konkrete Datums- und Uhrzeitangaben werden bevorzugt. Alternativen bitte mit angeben.">
        <FTextarea value={data.preferred_dates} onChange={v => set('preferred_dates', v)} disabled={disabled} rows={3}
          placeholder="z.B. Samstage im Oktober, bevorzugt 10–13 Uhr; alternativ November-Wochenenden" />
      </Field>
    </FormSection>
  )

  const sectionDetails = (
    <FormSection title="Kurs-Details" defaultOpen={true}>
      <label style={{ display:'flex', alignItems:'flex-start', gap:8, cursor:'pointer' }}>
        <input type="checkbox" checked={data.is_basic_course} onChange={e => set('is_basic_course', e.target.checked)} disabled={disabled} style={{ marginTop:2, flexShrink:0 }} />
        <div>
          <span style={{ fontSize:14, fontWeight:500, color:'#111827' }}>Dieser Kurs ist ein Grundlagenkurs</span>
          <p style={{ fontSize:12, color:'#6b7280', margin:'2px 0 0 0', textWrap:'pretty' }}>Pflichteinweisung für bestimmte Maschinen oder Räume (z.B. Lasercutter, Tischkreissäge).</p>
        </div>
      </label>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <Field label="Max. Teilnehmerzahl" required changed={changed.has('max_participants')}>
          <FInput type="number" value={String(data.max_participants)} onChange={v => set('max_participants', parseInt(v)||0)} disabled={disabled} />
        </Field>
        <Field label="Materialkosten pro Person (EUR)" changed={changed.has('material_cost_eur')} hint="0.00 wenn keine Kosten anfallen.">
          <FInput type="number" value={data.material_cost_eur} onChange={v => set('material_cost_eur', v)} disabled={disabled} />
        </Field>
      </div>
    </FormSection>
  )

  const sectionReferenten = (
    <FormSection title="Referent:innen" defaultOpen={true} badge={data.speakers.length === 0 ? 'Pflichtfeld' : undefined}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap:10, flexWrap:'wrap' }}>
        <p style={{ fontSize:13, color:'#6b7280', margin:0, textWrap:'pretty', maxWidth:440 }}>
          Alle Personen, die das Angebot durchführen. Die Kurzbiografie wird auf der Website veröffentlicht (mind. 50 Zeichen).
        </p>
        {!disabled && !alreadySpeaker && (
          <Btn variant="ghost" small onClick={handleAddSelf}>+ Mich als Referent:in eintragen</Btn>
        )}
      </div>
      {data.speakers.length > 0 && (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {data.speakers.map(s => (
            <SpeakerCard key={s.id} speaker={s} onRemove={id => set('speakers', data.speakers.filter(x => x.id !== id))} disabled={disabled} />
          ))}
        </div>
      )}
      {!disabled && (
        <div style={{ background:'#f9fafb', border:'1px dashed #d1d5db', borderRadius:8, padding:16 }}>
          <p style={{ fontSize:13, fontWeight:600, color:'#374151', margin:'0 0 12px 0' }}>Weitere Referent:in hinzufügen</p>
          <AddSpeakerInline onAdd={s => set('speakers', [...data.speakers, s])} />
        </div>
      )}
    </FormSection>
  )

  const sectionMitarbeiter = (
    <FormSection title="Mitbearbeiter:innen (optional)" defaultOpen={false}>
      <Field hint="Mitbearbeiter:innen können diesen Vorschlag einsehen und bearbeiten. Einladung erfolgt per E-Mail – kein Account nötig.">
        <EditorInvite editors={data.editors}
          onAdd={email => set('editors', [...data.editors, { id: Date.now(), email, name: email }])}
          onRemove={id => set('editors', data.editors.filter(e => (e.id||e.email) !== id))}
          disabled={disabled} />
      </Field>
      <div style={{ paddingTop:12, borderTop:'1px solid #f3f4f6', display:'flex', flexDirection:'column', gap:8 }}>
        <p style={{ fontSize:13, fontWeight:600, color:'#374151', margin:0 }}>Mitgliedschaft</p>
        <label style={{ display:'flex', alignItems:'center', gap:8, fontSize:13, cursor:'pointer' }}>
          <input type="checkbox" checked={data.is_regular_member} onChange={e => set('is_regular_member', e.target.checked)} disabled={disabled} />
          Ich bin ordentliches Mitglied bei ZAM
        </label>
        <label style={{ display:'flex', alignItems:'center', gap:8, fontSize:13, cursor:'pointer' }}>
          <input type="checkbox" checked={data.has_building_access} onChange={e => set('has_building_access', e.target.checked)} disabled={disabled} />
          Ich habe Gebäudezugang
        </label>
      </div>
    </FormSection>
  )

  const allSections = (
    <>
      {warningBanner}
      {sectionAllgemein}
      {sectionZeitplanung}
      {sectionDetails}
      {sectionReferenten}
      {sectionMitarbeiter}
      {saveBar}
    </>
  )

  // ── LAYOUT A: Split (form + sticky checklist)
  if (layout === 'split') {
    return (
      <div style={{ display:'grid', gridTemplateColumns:'1fr 270px', gap:24, alignItems:'start' }}>
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>{allSections}</div>
        <div style={{ position:'sticky', top:20 }}><ChecklistPanel formData={data} /></div>
      </div>
    )
  }

  // ── LAYOUT B: Stack (form then checklist)
  if (layout === 'stack') {
    return (
      <div style={{ display:'flex', flexDirection:'column', gap:14, maxWidth:780 }}>
        {allSections}
        <ChecklistPanel formData={data} />
      </div>
    )
  }

  // ── LAYOUT C: Wizard / Schrittweise
  const STEPS = [
    { label:'Allgemeines', sections: [sectionAllgemein, sectionDetails] },
    { label:'Zeitplanung',  sections: [sectionZeitplanung] },
    { label:'Referent:innen', sections: [sectionReferenten, sectionMitarbeiter] },
    { label:'Einreichen', sections: [] },
  ]

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16, maxWidth:780 }}>
      {/* Step indicator */}
      <div style={{ display:'flex', gap:0 }}>
        {STEPS.map((s, i) => (
          <button key={s.label} type="button" onClick={() => setWizardStep(i)}
            style={{ flex:1, padding:'10px 8px', background:'none', border:'none', borderBottom:`2px solid ${i===wizardStep ? '#646cff' : '#e5e7eb'}`,
              color: i===wizardStep ? '#646cff' : i < wizardStep ? '#374151' : '#9ca3af',
              fontFamily:'inherit', fontSize:13, fontWeight: i===wizardStep ? 700 : 500, cursor:'pointer', transition:'all 150ms' }}>
            <span style={{ display:'inline-flex', alignItems:'center', gap:5 }}>
              <span style={{ width:18, height:18, borderRadius:'50%', display:'inline-flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700,
                background: i < wizardStep ? '#16a34a' : i===wizardStep ? '#646cff' : '#e5e7eb',
                color: i <= wizardStep ? '#fff' : '#9ca3af' }}>
                {i < wizardStep ? '✓' : i+1}
              </span>
              {s.label}
            </span>
          </button>
        ))}
      </div>

      {wizardStep < 3 ? (
        <>
          {warningBanner}
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {STEPS[wizardStep].sections}
          </div>
          <div style={{ display:'flex', gap:10, paddingTop:8 }}>
            {wizardStep > 0 && <Btn variant="muted" onClick={() => setWizardStep(w => w-1)}>← Zurück</Btn>}
            {wizardStep < 2 && <Btn variant="primary" onClick={() => setWizardStep(w => w+1)}>Weiter →</Btn>}
            {wizardStep === 2 && <Btn variant="primary" onClick={() => setWizardStep(3)}>Zur Zusammenfassung →</Btn>}
            {hasChanges && <Btn variant="success" onClick={() => { setSaved(true); setChanged(new Set()) }}>Entwurf speichern</Btn>}
          </div>
        </>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
          {warningBanner}
          <ChecklistPanel formData={data} />
          <div style={{ background:'#fff', border:'1px solid #e5e7eb', borderRadius:8, padding:20, display:'flex', flexDirection:'column', gap:12 }}>
            <h3 style={{ fontSize:16, fontWeight:700, margin:0 }}>Bereit zum Einreichen?</h3>
            {allOk ? (
              <>
                <p style={{ fontSize:14, color:'#166534', margin:0 }}>✓ Alle Pflichtfelder sind ausgefüllt. Du kannst den Vorschlag jetzt einreichen.</p>
                <div style={{ display:'flex', gap:10 }}>
                  <Btn variant="primary" onClick={() => alert('Demo: Vorschlag eingereicht!')}>Vorschlag einreichen →</Btn>
                </div>
              </>
            ) : (
              <p style={{ fontSize:14, color:'#6b7280', margin:0 }}>Bitte alle Pflichtfelder ausfüllen, um einreichen zu können.</p>
            )}
          </div>
          <div style={{ display:'flex', gap:10 }}>
            <Btn variant="muted" onClick={() => setWizardStep(2)}>← Zurück</Btn>
            {hasChanges && <Btn variant="success" onClick={() => { setSaved(true); setChanged(new Set()) }}>Entwurf speichern</Btn>}
            {saved && !hasChanges && <span style={{ fontSize:13, color:'#16a34a', fontWeight:500 }}>✓ Gespeichert</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Proposal Editor View ─────────────────────────────────────────────────────
function ProposalEditorView({ proposals, selectedId, onSelect, onNew, layout }) {
  const proposal = proposals.find(p => p.id === selectedId) || proposals[0]

  return (
    <div style={{ display:'flex', height:'calc(100vh - 56px)', overflow:'hidden' }}>
      {/* Sidebar */}
      <aside style={{ width:240, flexShrink:0, background:'#fff', borderRight:'1px solid #e5e7eb',
        display:'flex', flexDirection:'column', overflow:'hidden' }}>
        <div style={{ padding:'16px 16px 10px', borderBottom:'1px solid #f3f4f6' }}>
          <p style={{ fontSize:12, fontWeight:700, color:'#9ca3af', textTransform:'uppercase', letterSpacing:'.05em', margin:'0 0 10px 0' }}>Vorschläge</p>
          <Btn variant="primary" small full onClick={onNew}>+ Neuer Vorschlag</Btn>
        </div>
        <ul style={{ flex:1, overflowY:'auto', listStyle:'none', padding:'8px 0', margin:0 }}>
          {proposals.map(p => {
            const active = p.id === (proposal && proposal.id)
            return (
              <li key={p.id} onClick={() => onSelect(p.id)}
                style={{ padding:'10px 16px', cursor:'pointer', background: active ? '#eef2ff' : 'transparent',
                  borderLeft: active ? '3px solid #646cff' : '3px solid transparent',
                  transition:'all 150ms' }}>
                <div style={{ fontWeight: active ? 700 : 500, fontSize:13, color: active ? '#3730a3' : '#111827', lineHeight:1.3 }}>{p.title || 'Ohne Titel'}</div>
                <div style={{ display:'flex', alignItems:'center', gap:6, marginTop:4 }}>
                  <StatusBadge status={p.status} />
                  <span style={{ fontSize:11, color:'#9ca3af' }}>{formatRelative(p.lastModified)}</span>
                </div>
              </li>
            )
          })}
        </ul>
      </aside>

      {/* Main content */}
      <main style={{ flex:1, overflowY:'auto', padding:'28px 32px' }}>
        {proposal ? (
          <>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20, gap:12, flexWrap:'wrap' }}>
              <div>
                <h1 style={{ fontSize:20, fontWeight:800, color:'#111827', margin:'0 0 4px 0', lineHeight:1.2 }}>
                  {proposal.title || 'Ohne Titel'}
                </h1>
                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  <StatusBadge status={proposal.status} />
                  <span style={{ fontSize:12, color:'#9ca3af' }}>
                    Zuletzt bearbeitet {formatRelative(proposal.lastModified)}
                  </span>
                </div>
              </div>
            </div>
            <ProposalFormContent initialData={proposal} disabled={false} layout={layout} />
          </>
        ) : (
          <div style={{ textAlign:'center', padding:60, color:'#9ca3af' }}>
            <p style={{ fontSize:24, marginBottom:8 }}>📋</p>
            <p style={{ fontSize:15 }}>Kein Vorschlag ausgewählt.<br/>Wähle links einen aus oder erstelle einen neuen.</p>
          </div>
        )}
      </main>
    </div>
  )
}

Object.assign(window, { Navbar, HomeScreen, ProposalEditorView, ProposalFormContent })
