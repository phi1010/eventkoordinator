import React, { useMemo, useState, useRef, useEffect } from "react";
import type { CalendarEvent, Resource } from "./calendarTypes";
import styles from "./WeekViewCombined.module.css";

interface WeekViewCombinedProps {
  resources: Resource[];
  events: CalendarEvent[];
  /** Optional date to seed the initial week (shows the week containing this date). Defaults to today. */
  startDate?: Date;
  /** Called when the user drags to create a new event. Receives the new event without an id. */
  onEventCreate?: (event: Omit<CalendarEvent, "id">) => void;
  /** Called when the displayed week changes. Range is returned as UTC ISO strings. */
  onWeekRangeChange?: (range: { startUtc: string; endUtc: string }) => void;
  /** When true, disables drag-and-drop event creation */
  disabled?: boolean;
}

interface DragState {
  resourceId: string;
  anchorDayIndex: number;
  anchorMinutes: number;
  currentDayIndex: number;
  currentMinutes: number;
}

interface PositionedEvent {
  ev: CalendarEvent;
  topPx: number;
  heightPx: number;
  leftPx: number;
  widthPx: number;
  color: string;
}

/** Pixels per 5-minute slot. */
const SLOT_PX = 2;
/** Minutes per slot. */
const SLOT_MIN = 5;
/** Pixel height of one full hour (12 slots × 2 px = 24 px). */
const HOUR_PX = (60 / SLOT_MIN) * SLOT_PX; // 24 px
/** Total pixel height of one full day. */
const DAY_H_PX = 24 * HOUR_PX; // 576 px
/** Width of the sticky time-gutter column. */
const GUTTER_PX = 52;
/** Default/fallback total width of each day column (used before first measurement). */
const COL_PX = 140;
/** Right strip (px) reserved as an empty drag-to-create zone. */
const DRAG_STRIP_PX = 16;
/** Milliseconds per minute. */
const MS_PER_MIN = 60_000;
/** Minimum height of the drag preview block in slots (10 min visible). */
const MIN_PREVIEW_SLOTS = 2;
/** Minimum day-column width (px) before switching to the stacked layout. */
const MIN_COL_PX = 100;
/** Height (px) of each day-section header in the stacked layout. */
const STACKED_SECTION_HDR_PX = 26;
/** Total height (px) of one stacked day section: header + column body. */
const STACKED_SECTION_H = STACKED_SECTION_HDR_PX + DAY_H_PX;

const WEEKDAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

const HOURS_24 = Array.from({ length: 24 }, (_, i) => i);

function getWeekMonday(date: Date): Date {
  const dow = date.getDay(); // 0 = Sun
  const delta = dow === 0 ? -6 : 1 - dow;
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + delta);
}

function addDays(date: Date, n: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

function fmtHour(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

/** Convert a y-pixel offset (within the day column body) to a snapped minute value. */
function pxToMinutes(y: number): number {
  const rawMinutes = (y / SLOT_PX) * SLOT_MIN;
  return Math.max(0, Math.min(24 * 60, Math.round(rawMinutes / SLOT_MIN) * SLOT_MIN));
}

/** Convert a 6-digit hex color to an rgba() string. */
function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.replace("#", ""), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export const WeekViewCombined: React.FC<WeekViewCombinedProps> = ({
  resources,
  events,
  startDate,
  onEventCreate,
  onWeekRangeChange,
  disabled = false,
}) => {
  const resourceMap = useMemo(
    () => new Map(resources.map(r => [r.id, r])),
    [resources],
  );

  const initWeekStart = useMemo(
    () => getWeekMonday(startDate ?? new Date()),
    [startDate],
  );

  const [weekStart, setWeekStart] = useState(initWeekStart);

  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );

  /** Resource to assign when the user drags to create a new event. */
  const [selectedResourceId, setSelectedResourceId] = useState(
    () => resources[0]?.id ?? "",
  );

  const [tooltip, setTooltip] = useState<{
    ev: CalendarEvent;
    x: number;
    y: number;
  } | null>(null);

  // ── Container-width tracking ──────────────────────────────────────────────

  /** Measured width of the scroll area (updated by ResizeObserver). */
  const [containerWidth, setContainerWidth] = useState(0);

  /**
   * True when the container is too narrow to show all 7 days side-by-side
   * (each column would be narrower than MIN_COL_PX).
   */
  const isStacked = useMemo(
    () => containerWidth > 0 && containerWidth < GUTTER_PX + 7 * MIN_COL_PX,
    [containerWidth],
  );

  /** Width of each day column – fills the available space equally. */
  const colPx = useMemo(() => {
    if (containerWidth <= 0) return COL_PX; // before first measurement
    return isStacked
      ? containerWidth - GUTTER_PX  // full width when stacked (one column per section)
      : (containerWidth - GUTTER_PX) / 7;
  }, [containerWidth, isStacked]);

  /** Usable pixel width available for event rendering (column minus drag strip). */
  const usablePx = colPx - DRAG_STRIP_PX;

  const weekLabel = useMemo(() => {
    const last = addDays(weekStart, 6);
    if (weekStart.getMonth() === last.getMonth()) {
      return `${MONTH_SHORT[weekStart.getMonth()]} ${weekStart.getDate()}–${last.getDate()}, ${weekStart.getFullYear()}`;
    }
    return `${MONTH_SHORT[weekStart.getMonth()]} ${weekStart.getDate()} – ${MONTH_SHORT[last.getMonth()]} ${last.getDate()}, ${weekStart.getFullYear()}`;
  }, [weekStart]);

  useEffect(() => {
    if (!onWeekRangeChange) return;
    const weekEnd = addDays(weekStart, 7);
    onWeekRangeChange({
      startUtc: weekStart.toISOString(),
      endUtc: weekEnd.toISOString(),
    });
  }, [onWeekRangeChange, weekStart]);

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

  /**
   * Compute positioned events for a single day column.
   *
   * Algorithm:
   * 1. Collect all events (all resources) that fall on `day`.
   * 2. Sort by start time.
   * 3. Assign each event a horizontal "slot index" using a greedy column packing
   *    (events that don't overlap can reuse the same slot index).
   * 4. For each event, find the maximum slot index among all events concurrent
   *    with it – that gives the total column count for its overlap group.
   * 5. Width  = usablePx / numCols
   *    Left   = slotIndex × width
   */
  function layoutDayEvents(day: Date): PositionedEvent[] {
    const dayMs    = day.getTime();
    const dayEndMs = dayMs + 86_400_000;

    const raw = visibleEvents
      .filter(ev =>
        new Date(ev.startUtc).getTime() < dayEndMs &&
        new Date(ev.endUtc).getTime()   > dayMs,
      )
      .map(ev => {
        const clampedStart = Math.max(new Date(ev.startUtc).getTime(), dayMs);
        const clampedEnd   = Math.min(new Date(ev.endUtc).getTime(), dayEndMs);
        const startMin = (clampedStart - dayMs) / MS_PER_MIN;
        const endMin   = (clampedEnd   - dayMs) / MS_PER_MIN;
        const topPx    = (startMin / SLOT_MIN) * SLOT_PX;
        const heightPx = Math.max(SLOT_PX, ((endMin - startMin) / SLOT_MIN) * SLOT_PX);
        return { ev, topPx, heightPx, startMin, endMin };
      })
      .sort((a, b) => a.startMin - b.startMin || b.endMin - a.endMin);

    // Greedy column-slot assignment.
    const slotEnds: number[] = [];  // slotEnds[i] = endMin of the last event in slot i
    const slotIdx: number[]  = [];  // slotIdx[i]  = assigned slot for raw[i]

    for (const item of raw) {
      let placed = false;
      for (let i = 0; i < slotEnds.length; i++) {
        if (slotEnds[i] <= item.startMin) {
          slotEnds[i] = item.endMin;
          slotIdx.push(i);
          placed = true;
          break;
        }
      }
      if (!placed) {
        slotIdx.push(slotEnds.length);
        slotEnds.push(item.endMin);
      }
    }

    // Build overlap groups (connected components) so that transitively
    // overlapping events all share the same column count.  Without this,
    // an early event that only directly overlaps one neighbour would get
    // a wider column than later events in the same chain.
    const groupOf = new Int32Array(raw.length);
    for (let i = 0; i < raw.length; i++) groupOf[i] = i;

    function findRoot(x: number): number {
      while (groupOf[x] !== x) { groupOf[x] = groupOf[groupOf[x]]; x = groupOf[x]; }
      return x;
    }
    function unite(a: number, b: number) {
      const ra = findRoot(a), rb = findRoot(b);
      if (ra !== rb) groupOf[ra] = rb;
    }

    for (let i = 0; i < raw.length; i++) {
      for (let j = i + 1; j < raw.length; j++) {
        if (raw[j].startMin < raw[i].endMin && raw[j].endMin > raw[i].startMin) {
          unite(i, j);
        }
      }
    }

    // For each group, find the maximum slot index → column count.
    const groupMaxSlot = new Map<number, number>();
    for (let i = 0; i < raw.length; i++) {
      const root = findRoot(i);
      groupMaxSlot.set(root, Math.max(groupMaxSlot.get(root) ?? 0, slotIdx[i]));
    }

    // Map each event to its final position.
    return raw.map((item, i) => {
      const numCols  = (groupMaxSlot.get(findRoot(i)) ?? 0) + 1;
      const colWidth = usablePx / numCols;
      const resource = resourceMap.get(item.ev.resourceId);

      return {
        ev:       item.ev,
        topPx:    item.topPx,
        heightPx: item.heightPx,
        leftPx:   slotIdx[i] * colWidth,
        widthPx:  Math.max(1, colWidth - 1), // 1 px gap between adjacent events
        color:    item.ev.color ?? resource?.color ?? "#4f46e5",
      };
    });
  }

  function handleMouseEnter(e: React.MouseEvent, ev: CalendarEvent) {
    if (dragRef.current) return;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setTooltip({ ev, x: r.left + r.width / 2, y: r.top });
  }

  // ── Drag-to-create ──────────────────────────────────────────────────────────

  const [dragPreview, setDragPreview] = useState<DragState | null>(null);
  const dragRef        = useRef<DragState | null>(null);
  const scrollRef      = useRef<HTMLDivElement>(null);
  const headerRef      = useRef<HTMLDivElement>(null);
  const weekDaysRef      = useRef(weekDays);
  const onEventCreateRef = useRef(onEventCreate);
  const isStackedRef     = useRef(isStacked);
  const colPxRef         = useRef(colPx);

  useEffect(() => {
    weekDaysRef.current      = weekDays;
    onEventCreateRef.current = onEventCreate;
    isStackedRef.current     = isStacked;
    colPxRef.current         = colPx;
  });

  // ── ResizeObserver: measure scroll area width ─────────────────────────────

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setContainerWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  function initDrag(clientY: number, dayIndex: number) {
    if (!selectedResourceId) return;
    const scroll = scrollRef.current;
    if (!scroll) return;
    const rect = scroll.getBoundingClientRect();
    let y: number;
    if (isStacked) {
      // In stacked mode each day section has its own header above the column body.
      y = clientY - rect.top + scroll.scrollTop - dayIndex * STACKED_SECTION_H - STACKED_SECTION_HDR_PX;
    } else {
      const headerH = headerRef.current?.offsetHeight ?? 0;
      y = clientY - rect.top + scroll.scrollTop - headerH;
    }
    const minutes = pxToMinutes(y);
    const state: DragState = {
      resourceId:      selectedResourceId,
      anchorDayIndex:  dayIndex,
      anchorMinutes:   minutes,
      currentDayIndex: dayIndex,
      currentMinutes:  minutes,
    };
    dragRef.current = state;
    setDragPreview(state);
    setTooltip(null);
  }

  useEffect(() => {
    function getCoords(clientX: number, clientY: number) {
      const scroll = scrollRef.current;
      if (!scroll) return null;
      const rect = scroll.getBoundingClientRect();

      if (isStackedRef.current) {
        // Stacked layout: day index is determined from the y position of the cursor.
        const y = clientY - rect.top + scroll.scrollTop;
        const dayIndex = Math.max(0, Math.min(6, Math.floor(y / STACKED_SECTION_H)));
        const yInColumn = y - dayIndex * STACKED_SECTION_H - STACKED_SECTION_HDR_PX;
        const rawMinutes = (yInColumn / SLOT_PX) * SLOT_MIN;
        const minutes = Math.max(0, Math.min(24 * 60, Math.round(rawMinutes / SLOT_MIN) * SLOT_MIN));
        return { dayIndex, minutes };
      }

      // Horizontal layout.
      const headerH = headerRef.current?.offsetHeight ?? 0;
      const x       = clientX - rect.left + scroll.scrollLeft - GUTTER_PX;
      const y       = clientY - rect.top  + scroll.scrollTop  - headerH;
      const rawMinutes = (y / SLOT_PX) * SLOT_MIN;
      const minutes  = Math.max(0, Math.min(24 * 60, Math.round(rawMinutes / SLOT_MIN) * SLOT_MIN));
      const dayIndex = Math.max(0, Math.min(6, Math.floor(x / colPxRef.current)));
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
          const anchorMs  = days[d.anchorDayIndex].getTime()  + d.anchorMinutes  * MS_PER_MIN;
          const currentMs = days[d.currentDayIndex].getTime() + d.currentMinutes * MS_PER_MIN;
          const startMs   = Math.min(anchorMs, currentMs);
          const endMs     = Math.max(anchorMs, currentMs);
          const finalEndMs = Math.max(endMs, startMs + SLOT_MIN * MS_PER_MIN);
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
      e.preventDefault();
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
  }, []); // handlers use refs for fresh values

  /** Return preview block dimensions for a given day column, or null. */
  function getDragPreview(day: Date): { topPx: number; heightPx: number } | null {
    if (!dragPreview) return null;
    const dayMs    = day.getTime();
    const dayEndMs = dayMs + 86_400_000;
    const anchorMs  = weekDays[dragPreview.anchorDayIndex].getTime()  + dragPreview.anchorMinutes  * MS_PER_MIN;
    const currentMs = weekDays[dragPreview.currentDayIndex].getTime() + dragPreview.currentMinutes * MS_PER_MIN;
    const startMs   = Math.min(anchorMs, currentMs);
    const endMs     = Math.max(anchorMs, currentMs);
    const finalEndMs = Math.max(endMs, startMs + SLOT_MIN * MS_PER_MIN);
    if (finalEndMs <= dayMs || startMs >= dayEndMs) return null;
    const clampedStart = Math.max(startMs, dayMs);
    const clampedEnd   = Math.min(finalEndMs, dayEndMs);
    const startMin = (clampedStart - dayMs) / MS_PER_MIN;
    const endMin   = (clampedEnd   - dayMs) / MS_PER_MIN;
    const topPx    = (startMin / SLOT_MIN) * SLOT_PX;
    const heightPx = Math.max(SLOT_PX * MIN_PREVIEW_SLOTS, ((endMin - startMin) / SLOT_MIN) * SLOT_PX);
    return { topPx, heightPx };
  }

  const selectedResource = resourceMap.get(selectedResourceId);

  /** Render the interior of a single day column (shared between horizontal and stacked layouts). */
  function renderDayCol(day: Date, di: number) {
    const dow        = day.getDay();
    const isWE       = dow === 0 || dow === 6;
    const positioned = layoutDayEvents(day);
    const preview    = getDragPreview(day);

    return (
      <div
        key={di}
        className={`${styles.wvcDayCol}${isWE ? ` ${styles.wvcDayColWe}` : ''}`}
        style={isStacked ? { flex: 1, height: DAY_H_PX } : { width: colPx, height: DAY_H_PX }}
        onMouseDown={e => {
          if (disabled) return;
          if ((e.target as HTMLElement).closest("[data-event]")) return;
          e.preventDefault();
          initDrag(e.clientY, di);
        }}
        onTouchStart={e => {
          if (disabled) return;
          if ((e.target as HTMLElement).closest("[data-event]")) return;
          initDrag(e.touches[0].clientY, di);
        }}
      >
        {/* Hour gridlines */}
        {HOURS_24.map(h => (
          <div key={h} className={styles.wvcHourLine} style={{ top: h * HOUR_PX }} aria-hidden="true" />
        ))}

        {/* Half-hour tick marks */}
        {HOURS_24.map(h => (
          <div key={h} className={styles.wvcHalfLine} style={{ top: h * HOUR_PX + HOUR_PX / 2 }} aria-hidden="true" />
        ))}

        {/* Events (all resources, overlap-laid out) */}
        {positioned.map(({ ev, topPx, heightPx, leftPx, widthPx, color }) => {
          const rotateTitle = heightPx > widthPx;

          return (
          <div
            key={ev.id}
            data-event="true"
            role="button"
            tabIndex={0}
            aria-label={`${ev.title}, ${fmtTime(ev.startUtc)}–${fmtTime(ev.endUtc)}`}
            className={`${styles.wvcEvent}${rotateTitle ? ` ${styles.wvcEventVertical}` : ''}`}
            style={{
              top:        topPx,
              height:     heightPx,
              left:       leftPx,
              width:      widthPx,
              background: color,
              border:     '1px solid rgba(255, 255, 255, 0.9)',
              boxSizing:  'border-box',
            }}
            onMouseEnter={e => handleMouseEnter(e, ev)}
            onMouseLeave={() => setTooltip(null)}
          >
            {heightPx >= HOUR_PX && (
              <span
                className={`${styles.wvcEventTitle}${rotateTitle ? ` ${styles.wvcEventTitleVertical}` : ''}`}
              >
                {ev.title}
              </span>
            )}
          </div>
          );
        })}

        {/* Drag strip – always-empty right zone for drag-to-create */}
        <div
          className={styles.wvcDragStrip}
          style={{ left: usablePx, width: DRAG_STRIP_PX }}
          aria-hidden="true"
        />

        {/* Drag preview – spans the full column width including the drag strip */}
        {preview && (
          <div
            className={styles.wvcDragPreview}
            aria-hidden="true"
            style={{
              top:    preview.topPx,
              height: preview.heightPx,
              right:  1,
              ...(selectedResource && {
                background:  hexToRgba(selectedResource.color, 0.2),
                borderColor: hexToRgba(selectedResource.color, 0.7),
              }),
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className={`${styles.wvcOuter}${dragPreview ? ` ${styles.wvcDragging}` : ''}`}>

      {/* ── Navigation ─────────────────────────────────────────────────────── */}
      <div className={styles.wvcNav}>
        <button
          className={styles.wvcNavBtn}
          onClick={() => setWeekStart(d => addDays(d, -7))}
          aria-label="Previous week"
        >&#8249;</button>
        <span className={styles.wvcWeekLabel}>{weekLabel}</span>
        <button
          className={styles.wvcNavBtn}
          onClick={() => setWeekStart(d => addDays(d, 7))}
          aria-label="Next week"
        >&#8250;</button>

        {/* Resource selector for drag-to-create */}
        {onEventCreate && resources.length > 0 && (
          <div className={styles.wvcResourceSelector}>
            <label className={styles.wvcCreateLabel} htmlFor="wvc-res-select">
              New events for:
            </label>
            <select
              id="wvc-res-select"
              className={styles.wvcResSelect}
              value={selectedResourceId}
              onChange={e => setSelectedResourceId(e.target.value)}
            >
              {resources.map(r => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
            {selectedResource && (
              <span
                className={styles.wvcResSwatch}
                style={{ background: selectedResource.color }}
              />
            )}
          </div>
        )}
      </div>

      {/* ── Resource legend ─────────────────────────────────────────────────── */}
      <div className={styles.wvcLegend} aria-label="Resource legend">
        {resources.map(r => (
          <span key={r.id} className={styles.wvcLegendItem}>
            <span className={styles.wvcDot} style={{ background: r.color }} aria-hidden="true" />
            <span className={styles.wvcLegendName}>{r.name}</span>
          </span>
        ))}
      </div>

      {/* ── Scrollable grid ────────────────────────────────────────────────── */}
      <div className={styles.wvcScrollArea} ref={scrollRef} aria-label="Calendar grid">
        <div className={styles.wvcInner} role="grid">

          {isStacked ? (
            /* ── Stacked layout: one day section per row ───────────────────── */
            weekDays.map((day, di) => {
              const dow  = day.getDay();
              const isWE = dow === 0 || dow === 6;
              return (
                <div key={di} className={styles.wvcStackedSection}>
                  {/* Day section header */}
                  <div className={`${styles.wvcStackedHdr}${isWE ? ` ${styles.wvcStackedHdrWe}` : ''}`}>
                    <div style={{ width: GUTTER_PX, minWidth: GUTTER_PX, flexShrink: 0 }} />
                    {WEEKDAY_SHORT[dow]}&nbsp;{day.getDate()}&nbsp;{MONTH_SHORT[day.getMonth()]}
                  </div>
                  {/* Day section body: gutter + column */}
                  <div className={styles.wvcBody}>
                    <div
                      className={styles.wvcGutter}
                      style={{ width: GUTTER_PX, minWidth: GUTTER_PX, height: DAY_H_PX }}
                    >
                      {HOURS_24.map(h => (
                        <div
                          key={h}
                          className={styles.wvcHourLabel}
                          style={{ top: h * HOUR_PX, height: HOUR_PX }}
                        >
                          {fmtHour(h)}
                        </div>
                      ))}
                    </div>
                    {renderDayCol(day, di)}
                  </div>
                </div>
              );
            })
          ) : (
            /* ── Horizontal layout: sticky header + body ───────────────────── */
            <>
              {/* Sticky header */}
              <div className={styles.wvcHeader} ref={headerRef}>
                <div className={styles.wvcCorner} style={{ width: GUTTER_PX, minWidth: GUTTER_PX }} />
                <div className={styles.wvcDayHeaders}>
                  {weekDays.map((day, di) => {
                    const dow  = day.getDay();
                    const isWE = dow === 0 || dow === 6;
                    return (
                      <div
                        key={di}
                        className={`${styles.wvcDayHdr}${isWE ? ` ${styles.wvcDayHdrWe}` : ''}`}
                        style={{ width: colPx }}
                      >
                        {WEEKDAY_SHORT[dow]}&nbsp;{day.getDate()}&nbsp;{MONTH_SHORT[day.getMonth()]}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Body: time gutter + day columns */}
              <div className={styles.wvcBody}>
                <div
                  className={styles.wvcGutter}
                  style={{ width: GUTTER_PX, minWidth: GUTTER_PX, height: DAY_H_PX }}
                >
                  {HOURS_24.map(h => (
                    <div
                      key={h}
                      className={styles.wvcHourLabel}
                      style={{ top: h * HOUR_PX, height: HOUR_PX }}
                    >
                      {fmtHour(h)}
                    </div>
                  ))}
                </div>
                {weekDays.map((day, di) => renderDayCol(day, di))}
              </div>
            </>
          )}

        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className={styles.wvcTooltip}
          style={{ left: tooltip.x, top: tooltip.y }}
          aria-hidden="true"
        >
          <strong>{tooltip.ev.title}</strong>
          <br />
          {fmtTime(tooltip.ev.startUtc)} – {fmtTime(tooltip.ev.endUtc)} local
          <br />
          <span className={styles.wvcTooltipDate}>
            {fmtDate(tooltip.ev.startUtc)}
          </span>
          <br />
          <span className={styles.wvcTooltipResource}>
            {resourceMap.get(tooltip.ev.resourceId)?.name ?? tooltip.ev.resourceId}
          </span>
        </div>
      )}
    </div>
  );
};

export default WeekViewCombined;
