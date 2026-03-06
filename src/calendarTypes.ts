export interface Resource {
  id: string;
  name: string;
  color: string;
}

export interface CalendarEvent {
  id: string;
  resourceId: string;
  title: string;
  /** ISO 8601 UTC datetime string, e.g. "2026-03-06T09:00:00Z" */
  startUtc: string;
  /** ISO 8601 UTC datetime string */
  endUtc: string;
  color?: string;
}
