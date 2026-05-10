import type { AlertsState, Event, QueryResult, Video, VideoStatus } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function uploadVideo(file: File, location: string, recordingStartTime: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("location", location);
  form.append("recording_start_time", recordingStartTime);
  return request<{ video: Video }>("/upload", { method: "POST", body: form });
}

export async function getVideoStatus(videoId: string) {
  return request<VideoStatus>(`/videos/${videoId}/status`);
}

export async function listEvents(videoId?: string) {
  const params = new URLSearchParams();
  if (videoId) params.set("video_id", videoId);
  return request<Event[]>(`/events?${params.toString()}`);
}

export async function askQuery(question: string, videoId?: string) {
  return request<QueryResult>("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, video_id: videoId ?? null }),
  });
}

export async function createAlert(text: string, cooldownSeconds?: number) {
  return request("/alert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, cooldown_seconds: cooldownSeconds ?? null }),
  });
}

export async function getAlerts() {
  return request<AlertsState>("/alerts");
}

export async function deleteAlertRule(ruleId: string) {
  return request(`/alerts/rules/${ruleId}`, { method: "DELETE" });
}

export async function clearAlertHits() {
  return request("/alerts/hits", { method: "DELETE" });
}

export type SeedResult = {
  video_id: string;
  created_events: number;
  created_rules: number;
  created_hits: number;
};

export async function seedDemo() {
  return request<SeedResult>("/seed", { method: "POST" });
}
