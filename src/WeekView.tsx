import React, { useMemo, useState, useRef, useEffect } from "react";
import type { CalendarEvent, Resource } from "./calendarTypes";
import styles from "./WeekView.module.css";

interface WeekViewProps {
  resources: Resource[];
  events: CalendarEvent[];
  /** Optional date to seed the initial week (shows the week containing this date). Defaults to today. */
  startDate?: Date;
  /** Called when the user drags to create a new event. Receives the new event without an id. */
  onEventCreate?: (event: Omit<CalendarEvent, "id">) => void;
}

interface DragState {
  resourceId: string;
  anchorDayIndex: number;
  anchorMinutes: number;
  currentDayIndex: number;
  currentMinutes: number;
}

/** Pixels per 5-minute slot (2 px × 1 slot). */
const SLOT_PX = 2;
/** Minutes per slot. */
const SLOT_MIN = 5;
/** Pixel height of one full hour (12 slots × 2 px = 24 px). */
const HOUR_PX = (60 / SLOT_MIN) * SLOT_PX; // 24 px
/** Total pixel height of one full day (24 hours × 24 px = 576 px). */
const DAY_H_PX = 24 * HOUR_PX; // 576 px
/** Width of the sticky time-gutter column. */
const GUTTER_PX = 52;
/** Width of each resource sub-column inside a day. */
const SUBCOL_PX = 60;

/** Sunday-first (index 0 = Sun) to align with Date.getUTCDay() return values. */
const WEEKDAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

const HOURS_24 = Array.from({ length: 24 }, (_, i) => i);

/** Return the UTC Monday of the ISO week containing `date`. */
function getWeekMonday(date: Date): Date {
  const dow = date.getUTCDay(); // 0 = Sun
  const delta = dow === 0 ? -6 : 1 - dow;
  return new Date(Date.UTC(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate() + delta,
  ));
}

function addDays(date: Date, n: number): Date {
  return new Date(Date.UTC(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate() + n,
  ));
}

function fmtHour(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export const WeekView: React.FC<WeekViewProps> = ({ resources, events, startDate, onEventCreate }) => {
  const initWeekStart = useMemo(
    () => getWeekMonday(startDate ?? new Date()),
    [startDate],
  );

  const [weekStart, setWeekStart] = useState(initWeekStart);

  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );

  const [tooltip, setTooltip] = useState<{
    ev: CalendarEvent;
    x: number;
    y: number;
  } | null>(null);

  const weekLabel = useMemo(() => {
    const last = addDays(weekStart, 6);
    if (weekStart.getUTCMonth() === last.getUTCMonth()) {
      return `${MONTH_SHORT[weekStart.getUTCMonth()]} ${weekStart.getUTCDate()}–${last.getUTCDate()}, ${weekStart.getUTCFullYear()}`;
    }
    return `${MONTH_SHORT[weekStart.getUTCMonth()]} ${weekStart.getUTCDate()} – ${MONTH_SHORT[last.getUTCMonth()]} ${last.getUTCDate()}, ${weekStart.getUTCFullYear()}`;
  }, [weekStart]);

  /** All events that overlap the currently displayed week. */
  const visibleEvents = useMemo(() => {
    const startMs = weekStart.getTime();
    const endMs   = startMs + 7 * 86_400_000;
    return events.filter(ev => {
      const s = new Date(ev.startUtc).getTime();
      const e = new Date(ev.endUtc).getTime();
      return s < endMs && e > startMs;
    });
  }, [events, weekStart]);

  /** Return positioned events for a single (day, resource) cell. */
  function cellEvents(day: Date, resourceId: string) {
    const dayMs    = day.getTime();
    const dayEndMs = dayMs + 86_400_000;
    return visibleEvents
      .filter(ev =>
        ev.resourceId === resourceId &&
        new Date(ev.startUtc).getTime() < dayEndMs &&
        new Date(ev.endUtc).getTime()   > dayMs,
      )
      .map(ev => {
        const clampedStart = Math.max(new Date(ev.startUtc).getTime(), dayMs);
        const clampedEnd   = Math.min(new Date(ev.endUtc).getTime(), dayEndMs);
        const startMin = (clampedStart - dayMs) / 60_000;
        const endMin   = (clampedEnd   - dayMs) / 60_000;
        const topPx    = (startMin / SLOT_MIN) * SLOT_PX;
        const heightPx = Math.max(SLOT_PX, ((endMin - startMin) / SLOT_MIN) * SLOT_PX);
        return { ev, topPx, heightPx };
      });
  }

  function handleMouseEnter(e: React.MouseEvent, ev: CalendarEvent) {
    if (dragRef.current) return; // suppress tooltip while dragging
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setTooltip({ ev, x: r.left + r.width / 2, y: r.top });
  }

  const dayColW = resources.length * SUBCOL_PX;
  const totalW  = GUTTER_PX + 7 * dayColW;

  // ── Drag-to-create ──────────────────────────────────────────────────────────

  const [dragPreview, setDragPreview] = useState<DragState | null>(null);
  /** Always-fresh ref used inside document-level event handlers. */
  const dragRef = useRef<DragState | null>(null);
  /** Ref to the scroll container for coordinate conversion. */
  const scrollRef = useRef<HTMLDivElement>(null);
  /** Ref to the sticky header so its height can be subtracted from y-coordinate calculations. */
  const headerRef = useRef<HTMLDivElement>(null);

  /** Refs so that document-level handlers always read current values without extra deps. */
  const weekDaysRef      = useRef(weekDays);
  const onEventCreateRef = useRef(onEventCreate);
  const dayColWRef       = useRef(dayColW);
  // Sync refs in a layout effect so they are always fresh before any paint.
  useEffect(() => {
    weekDaysRef.current    = weekDays;
    onEventCreateRef.current = onEventCreate;
    dayColWRef.current     = dayColW;
  });

  /** Convert a y-pixel offset (within the day column) to a snapped minute value. */
  function pxToMinutes(y: number): number {
    const rawMinutes = (y / SLOT_PX) * SLOT_MIN;
    return Math.max(0, Math.min(24 * 60, Math.round(rawMinutes / SLOT_MIN) * SLOT_MIN));
  }

  /** Start a drag from a pointer position within a specific day/resource. */
  function initDrag(clientY: number, dayIndex: number, resourceId: string) {
    const scroll = scrollRef.current;
    if (!scroll) return;
    const rect = scroll.getBoundingClientRect();
    const headerH = headerRef.current?.offsetHeight ?? 0;
    const y = clientY - rect.top + scroll.scrollTop - headerH;
    const minutes = pxToMinutes(y);
    const state: DragState = {
      resourceId,
      anchorDayIndex:   dayIndex,
      anchorMinutes:    minutes,
      currentDayIndex:  dayIndex,
      currentMinutes:   minutes,
    };
    dragRef.current = state;
    setDragPreview(state);
    setTooltip(null);
  }

  // Register document-level mouse/touch handlers once; refs supply fresh values.
  useEffect(() => {
    function getCoords(clientX: number, clientY: number) {
      const scroll = scrollRef.current;
      if (!scroll) return null;
      const rect = scroll.getBoundingClientRect();
      const headerH = headerRef.current?.offsetHeight ?? 0;
      const x = clientX - rect.left + scroll.scrollLeft - GUTTER_PX;
      const y = clientY - rect.top  + scroll.scrollTop - headerH;
      const rawMinutes = (y / SLOT_PX) * SLOT_MIN;
      const minutes = Math.max(0, Math.min(24 * 60, Math.round(rawMinutes / SLOT_MIN) * SLOT_MIN));
      const dayIndex = Math.max(0, Math.min(6, Math.floor(x / dayColWRef.current)));
      return { dayIndex, minutes };
    }
    function updateDrag(clientX: number, clientY: number) {
      const d = dragRef.current;
      if (!d) return;
      const coords = getCoords(clientX, clientY);
      if (!coords) return;
      const updated: DragState = {
        ...d,
        currentDayIndex: coords.dayIndex,
        currentMinutes:  coords.minutes,
      };
      dragRef.current = updated;
      setDragPreview(updated);
    }

    function finishDrag() {
      const d = dragRef.current;
      if (d) {
        const cb = onEventCreateRef.current;
        if (cb) {
          const days      = weekDaysRef.current;
          const anchorMs  = days[d.anchorDayIndex].getTime()  + d.anchorMinutes  * 60_000;
          const currentMs = days[d.currentDayIndex].getTime() + d.currentMinutes * 60_000;
          const startMs   = Math.min(anchorMs, currentMs);
          const endMs     = Math.max(anchorMs, currentMs);
          // Enforce a minimum duration of one slot.
          const finalEndMs = Math.max(endMs, startMs + SLOT_MIN * 60_000);
          cb({
            resourceId: d.resourceId,
            title:      "New Event",
            startUtc:   new Date(startMs).toISOString(),
            endUtc:     new Date(finalEndMs).toISOString(),
          });
        }
      }
      dragRef.current = null;
      setDragPreview(null);
    }

    function onMouseMove(e: MouseEvent) { updateDrag(e.clientX, e.clientY); }
    function onMouseUp()                { finishDrag(); }
    function onTouchMove(e: TouchEvent) {
      if (!dragRef.current) return;
      e.preventDefault(); // prevent page scroll while dragging
      updateDrag(e.touches[0].clientX, e.touches[0].clientY);
    }
    function onTouchEnd(e: TouchEvent) {
      if (!dragRef.current) return;
      const t = e.changedTouches[0];
      updateDrag(t.clientX, t.clientY);
      finishDrag();
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup",   onMouseUp);
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend",  onTouchEnd);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup",   onMouseUp);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend",  onTouchEnd);
    };
  }, []); // handlers use refs for fresh values: scrollRef, dragRef, weekDaysRef, onEventCreateRef, dayColWRef

  /** Return the preview block dimensions for a given (day, resourceId) cell, or null. */
  function getDragPreview(day: Date, resourceId: string): { topPx: number; heightPx: number } | null {
    if (!dragPreview || resourceId !== dragPreview.resourceId) return null;
    const dayMs    = day.getTime();
    const dayEndMs = dayMs + 86_400_000;
    const anchorMs  = weekDays[dragPreview.anchorDayIndex].getTime()  + dragPreview.anchorMinutes  * 60_000;
    const currentMs = weekDays[dragPreview.currentDayIndex].getTime() + dragPreview.currentMinutes * 60_000;
    const startMs   = Math.min(anchorMs, currentMs);
    const endMs     = Math.max(anchorMs, currentMs);
    const finalEndMs = Math.max(endMs, startMs + SLOT_MIN * 60_000);
    if (finalEndMs <= dayMs || startMs >= dayEndMs) return null;
    const clampedStart = Math.max(startMs, dayMs);
    const clampedEnd   = Math.min(finalEndMs, dayEndMs);
    const startMin  = (clampedStart - dayMs) / 60_000;
    const endMin    = (clampedEnd   - dayMs) / 60_000;
    const topPx     = (startMin / SLOT_MIN) * SLOT_PX;
    const heightPx  = Math.max(SLOT_PX * 2, ((endMin - startMin) / SLOT_MIN) * SLOT_PX); // minimum 2 slots (10 min) visible
    return { topPx, heightPx };
  }

  return (
    <div className={`${styles.wvOuter}${dragPreview ? ` ${styles.wvDragging}` : ''}`}>

      {/* ── Navigation ─────────────────────────────────────────────────────── */}
      <div className={styles.wvNav}>
        <button
          className={styles.wvNavBtn}
          onClick={() => setWeekStart(d => addDays(d, -7))}
          aria-label="Previous week"
        >&#8249;</button>
        <span className={styles.wvWeekLabel}>{weekLabel}</span>
        <button
          className={styles.wvNavBtn}
          onClick={() => setWeekStart(d => addDays(d, 7))}
          aria-label="Next week"
        >&#8250;</button>
      </div>

      {/* ── Scrollable grid ────────────────────────────────────────────────── */}
      <div className={styles.wvScrollArea} ref={scrollRef} aria-label="Calendar grid">
        <div className={styles.wvInner} style={{ minWidth: totalW }} role="grid">

          {/* Sticky header: day titles + resource sub-headers */}
          <div className={styles.wvHeader} ref={headerRef} role="row">
            {/* Corner cell – sticky in both top and left */}
            <div className={styles.wvCorner} style={{ width: GUTTER_PX, minWidth: GUTTER_PX }} aria-hidden="true" />

            <div className={styles.wvDayHeaders}>
              {weekDays.map((day, di) => {
                const dow = day.getUTCDay();
                const isWE = dow === 0 || dow === 6;
                return (
                  <div
                    key={di}
                    role="columnheader"
                    className={`${styles.wvDayHdr}${isWE ? ` ${styles.wvDayHdrWe}` : ''}`}
                    style={{ width: dayColW, minWidth: dayColW }}
                  >
                    {/* Row 1: weekday name + date */}
                    <div className={styles.wvDayTitle}>
                      {WEEKDAY_SHORT[dow]}&nbsp;{day.getUTCDate()}&nbsp;{MONTH_SHORT[day.getUTCMonth()]}
                    </div>
                    {/* Row 2: one cell per resource */}
                    <div className={styles.wvSubcolHeaders}>
                      {resources.map(r => (
                        <div
                          key={r.id}
                          className={styles.wvSubcolHdr}
                          style={{ width: SUBCOL_PX, minWidth: SUBCOL_PX }}
                          title={r.name}
                        >
                          <span className={styles.wvDot} style={{ background: r.color }} aria-hidden="true" />
                          <span className={styles.wvSubcolName}>{r.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Body: time gutter + day columns */}
          <div className={styles.wvBody}>

            {/* Time gutter – sticky left, contains hour labels */}
            <div
              className={styles.wvGutter}
              style={{ width: GUTTER_PX, minWidth: GUTTER_PX, height: DAY_H_PX }}
              aria-hidden="true"
            >
              {/* One label per hour, each spanning HOUR_PX = 24 px (12 × 2 px slots). */}
              {HOURS_24.map(h => (
                <div
                  key={h}
                  className={styles.wvHourLabel}
                  style={{ top: h * HOUR_PX, height: HOUR_PX }}
                >
                  {fmtHour(h)}
                </div>
              ))}
            </div>

            {/* Seven day columns */}
            {weekDays.map((day, di) => {
              const dow = day.getUTCDay();
              const isWE = dow === 0 || dow === 6;
              return (
                <div
                  key={di}
                  role="gridcell"
                  aria-label={`${WEEKDAY_SHORT[dow]} ${day.getUTCDate()} ${MONTH_SHORT[day.getUTCMonth()]}`}
                  className={`${styles.wvDayCol}${isWE ? ` ${styles.wvDayColWe}` : ''}`}
                  style={{ width: dayColW, height: DAY_H_PX }}
                >
                  {/* Horizontal hour gridlines spanning the full day column */}
                  {HOURS_24.map(h => (
                    <div
                      key={h}
                      className={styles.wvHourLine}
                      style={{ top: h * HOUR_PX }}
                      aria-hidden="true"
                    />
                  ))}

                  {/* Half-hour tick marks (no label) */}
                  {HOURS_24.map(h => (
                    <div
                      key={h}
                      className={styles.wvHalfLine}
                      style={{ top: h * HOUR_PX + HOUR_PX / 2 }}
                      aria-hidden="true"
                    />
                  ))}

                  {/* Resource sub-columns, one per resource */}
                  {resources.map((resource, ri) => {
                    const preview = getDragPreview(day, resource.id);
                    return (
                      <div
                        key={resource.id}
                        className={styles.wvSubcol}
                        style={{ left: ri * SUBCOL_PX, width: SUBCOL_PX }}
                        onMouseDown={e => {
                          if ((e.target as HTMLElement).closest("[data-event]")) return;
                          e.preventDefault();
                          initDrag(e.clientY, di, resource.id);
                        }}
                        onTouchStart={e => {
                          if ((e.target as HTMLElement).closest("[data-event]")) return;
                          initDrag(e.touches[0].clientY, di, resource.id);
                        }}
                      >
                        {cellEvents(day, resource.id).map(({ ev, topPx, heightPx }) => (
                          <div
                            key={ev.id}
                            data-event="true"
                            role="button"
                            tabIndex={0}
                            aria-label={`${ev.title}, ${fmtTime(ev.startUtc)}–${fmtTime(ev.endUtc)} UTC`}
                            className={styles.wvEvent}
                            style={{
                              top: topPx,
                              height: heightPx,
                              background: ev.color ?? resource.color,
                            }}
                            onMouseEnter={e => handleMouseEnter(e, ev)}
                            onMouseLeave={() => setTooltip(null)}
                          >
                            {/* Show title only when the event block is at least one hour tall */}
                            {heightPx >= HOUR_PX && (
                              <span className={styles.wvEventTitle} aria-hidden="true">{ev.title}</span>
                            )}
                          </div>
                        ))}
                        {preview && (
                          <div
                            className={styles.wvDragPreview}
                            style={{ top: preview.topPx, height: preview.heightPx }}
                            aria-hidden="true"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className={styles.wvTooltip}
          style={{ left: tooltip.x, top: tooltip.y }}
          aria-hidden="true"
        >
          <strong>{tooltip.ev.title}</strong>
          <br />
          {fmtTime(tooltip.ev.startUtc)} – {fmtTime(tooltip.ev.endUtc)} UTC
          <br />
          <span className={styles.wvTooltipDate}>
            {new Date(tooltip.ev.startUtc).toISOString().slice(0, 10)}
          </span>
        </div>
      )}
    </div>
  );
};

export default WeekView;
