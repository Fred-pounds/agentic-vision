export type Video = {
  id: string;
  filename: string;
  location: string;
  recording_start_time: string;
  status: string;
  progress: number;
};

export type VideoStatus = {
  video_id: string;
  status: string;
  progress: number;
  current_time_seconds: number;
  event_count: number;
  alert_count: number;
  error?: string | null;
};

export type Event = {
  id: string;
  video_id: string;
  timestamp_seconds: number;
  timestamp_iso: string;
  objects: string[];
  track_ids: string[];
  caption: string;
  location: string;
  frame_path?: string | null;
  confidence_summary: Record<string, number>;
};

export type QueryResult = {
  answer: string;
  supporting_events: Event[];
  used_fallback: boolean;
};

export type AlertRule = {
  id: string;
  text: string;
  object_keywords: string[];
  cooldown_seconds: number;
  enabled: boolean;
};

export type AlertHit = {
  id: string;
  rule_id: string;
  event_id: string;
  message: string;
  timestamp_iso: string;
};

export type AlertsState = {
  rules: AlertRule[];
  hits: AlertHit[];
};

