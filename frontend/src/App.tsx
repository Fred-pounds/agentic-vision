import { useEffect, useMemo, useRef, useState } from "react";
import {
  askQuery,
  createAlert,
  getAlerts,
  getVideoStatus,
  listEvents,
  seedDemo,
  uploadVideo,
} from "./api/client";
import type { AlertHit, AlertRule, AlertsState, Event, QueryResult, Video, VideoStatus } from "./types";
import { useSpeechRecognition } from "./hooks/useSpeechRecognition";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  fallback?: boolean;
  events?: Event[];
};

type DictationTarget = "query" | "alert";

export default function App() {
  const [video, setVideo] = useState<Video | null>(null);
  const [status, setStatus] = useState<VideoStatus | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [alerts, setAlerts] = useState<AlertsState>({ rules: [], hits: [] });
  const [chat, setChat] = useState<ChatMessage[]>([
    { role: "assistant", text: "Upload a video, ask a question, or seed demo data to start." },
  ]);
  const [query, setQuery] = useState("");
  const [alertText, setAlertText] = useState("");
  const [location, setLocation] = useState("office");
  const [recordingStart, setRecordingStart] = useState("");
  const [busy, setBusy] = useState(false);
  const [voiceTarget, setVoiceTarget] = useState<DictationTarget>("query");
  const [speechEnabled, setSpeechEnabled] = useState(true);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const pollingRef = useRef<number | null>(null);
  const speech = useSpeechRecognition();
  const canDictate = speech.supported;

  useEffect(() => {
    void refreshAlerts();
  }, []);

  useEffect(() => {
    if (!video) return;
    if (pollingRef.current) window.clearInterval(pollingRef.current);
    const poll = async () => {
      try {
        const [nextStatus, nextEvents, nextAlerts] = await Promise.all([
          getVideoStatus(video.id),
          listEvents(video.id),
          getAlerts(),
        ]);
        setStatus(nextStatus);
        setEvents(nextEvents.reverse());
        setAlerts(nextAlerts);
      } catch {
        // Leave the last known state on screen.
      }
    };
    void poll();
    pollingRef.current = window.setInterval(poll, 1500);
    return () => {
      if (pollingRef.current) window.clearInterval(pollingRef.current);
    };
  }, [video]);

  useEffect(() => {
    if (!speech.transcript) return;
    if (voiceTarget === "query") {
      setQuery(speech.transcript);
    } else {
      setAlertText(speech.transcript);
    }
  }, [speech.transcript, voiceTarget]);

  const streaming = useMemo(() => {
    if (!status) return false;
    return status.status === "queued" || status.status === "processing";
  }, [status]);

  async function refreshAlerts() {
    try {
      setAlerts(await getAlerts());
    } catch {
      // Ignore on first load if backend is still coming up.
    }
  }

  async function handleUpload() {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const response = await uploadVideo(file, location, recordingStart || new Date().toISOString());
      setVideo(response.video);
      setStatus({
        video_id: response.video.id,
        status: response.video.status,
        progress: response.video.progress,
        current_time_seconds: 0,
        event_count: 0,
        alert_count: 0,
      });
      setChat((prev) => [...prev, { role: "assistant", text: `Processing ${file.name}. The timeline will update as the video is analyzed.` }]);
    } finally {
      setBusy(false);
    }
  }

  async function handleQuery() {
    const question = query.trim();
    if (!question) return;
    setBusy(true);
    setChat((prev) => [...prev, { role: "user", text: question }]);
    try {
      const response = await askQuery(question, video?.id);
      appendAnswer(response);
      if (speechEnabled) speak(response.answer);
      setQuery("");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateAlert() {
    const text = alertText.trim();
    if (!text) return;
    setBusy(true);
    try {
      await createAlert(text);
      setAlertText("");
      await refreshAlerts();
    } finally {
      setBusy(false);
    }
  }

  async function handleSeed() {
    setBusy(true);
    try {
      const response = await seedDemo();
      setVideo({
        id: response.video_id,
        filename: "seed-demo.mp4",
        location: "office",
        recording_start_time: new Date().toISOString(),
        status: "completed",
        progress: 1,
      });
      setStatus({
        video_id: response.video_id,
        status: "completed",
        progress: 1,
        current_time_seconds: 36,
        event_count: response.created_events,
        alert_count: response.created_hits,
      });
      await refreshAlerts();
      const nextEvents = await listEvents(response.video_id);
      setEvents(nextEvents.reverse());
    } finally {
      setBusy(false);
    }
  }

  function appendAnswer(response: QueryResult) {
    setChat((prev) => [
      ...prev,
      { role: "assistant", text: response.answer, fallback: response.used_fallback, events: response.supporting_events },
    ]);
  }

  function speak(text: string) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }

  function startDictation(target: DictationTarget) {
    setVoiceTarget(target);
    speech.setTranscript("");
    speech.start();
  }

  const visibleEvents = events.length > 0 ? events : [];

  return (
    <div className="app-shell">
      <div className="bg-orb orb-a" />
      <div className="bg-orb orb-b" />

      <header className="topbar">
        <div>
          <p className="eyebrow">Vision Assistant</p>
          <h1>Multimodal video memory with voice, alerts, and timeline retrieval.</h1>
        </div>
        <div className={`status-pill ${streaming ? "live" : ""}`}>{streaming ? "Processing live" : "Idle"}</div>
      </header>

      <main className="grid">
        <section className="panel hero-panel">
          <div className="panel-header">
            <h2>Upload</h2>
            <button className="secondary" onClick={handleSeed} disabled={busy}>
              Load demo memory
            </button>
          </div>
          <div className="upload-card">
            <input ref={fileInput} type="file" accept="video/*" />
            <div className="field-row">
              <label>
                Location
                <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="office" />
              </label>
              <label>
                Recording start
                <input
                  value={recordingStart}
                  onChange={(e) => setRecordingStart(e.target.value)}
                  placeholder="2026-05-06T12:00:00Z"
                />
              </label>
            </div>
            <button onClick={handleUpload} disabled={busy}>
              {busy ? "Working..." : "Upload video"}
            </button>
          </div>

          <div className="progress-block">
            <div className="progress-meta">
              <span>Processing status</span>
              <span>{status ? `${Math.round(status.progress * 100)}%` : "0%"}</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${Math.max(2, Math.round((status?.progress ?? 0) * 100))}%` }} />
            </div>
            <div className="status-grid">
              <Metric label="Video" value={video?.filename ?? "none"} />
              <Metric label="Events" value={String(status?.event_count ?? 0)} />
              <Metric label="Alerts" value={String(status?.alert_count ?? 0)} />
              <Metric label="Time" value={formatSeconds(status?.current_time_seconds ?? 0)} />
            </div>
            {status?.error ? <p className="error-copy">{status.error}</p> : null}
          </div>
        </section>

        <section className="panel timeline-panel">
          <div className="panel-header">
            <h2>Timeline</h2>
            <span className="subtle">{visibleEvents.length} events</span>
          </div>
          <div className="timeline-list">
            {visibleEvents.length === 0 ? (
              <EmptyState title="No events yet" description="Upload a video or seed demo data to populate the timeline." />
            ) : (
              visibleEvents.map((event) => (
                <article className="event-card" key={event.id}>
                  <div className="event-topline">
                    <strong>{formatTimestamp(event.timestamp_iso)}</strong>
                    <span>{event.location}</span>
                  </div>
                  <p className="event-caption">{event.caption}</p>
                  <div className="tag-row">
                    {event.objects.map((object) => (
                      <span className="tag" key={object}>
                        {object}
                      </span>
                    ))}
                  </div>
                  <div className="event-footer">
                    <span>{event.track_ids.length} tracks</span>
                    {event.frame_path ? <span className="mono">{event.frame_path.split("/").slice(-2).join("/")}</span> : null}
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="panel chat-panel">
          <div className="panel-header">
            <h2>Voice Query</h2>
            <div className="toggle-row">
            <button className="secondary" onClick={() => setSpeechEnabled((value) => !value)}>
              Voice {speechEnabled ? "on" : "off"}
            </button>
            <button className="secondary" onClick={() => startDictation("query")} disabled={!canDictate}>
              {speech.listening && voiceTarget === "query" ? "Listening..." : canDictate ? "Speak query" : "Mic unavailable"}
            </button>
          </div>
          </div>

          <div className="chat-log">
            {chat.map((message, index) => (
              <div className={`bubble ${message.role}`} key={`${message.role}-${index}`}>
                <p>{message.text}</p>
                {message.fallback ? <span className="pill warn">Fallback answer</span> : null}
                {message.events?.length ? (
                  <div className="supporting-events">
                    {message.events.slice(0, 3).map((event) => (
                      <span className="tag subtle-tag" key={event.id}>
                        {formatTimestamp(event.timestamp_iso)} · {event.caption}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <div className="composer">
            <textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Did anyone enter the room?" />
            <div className="actions">
              <button className="secondary" onClick={() => startDictation("query")} disabled={!canDictate}>
                {canDictate ? "Dictate" : "No mic"}
              </button>
              <button onClick={handleQuery} disabled={busy}>
                Ask
              </button>
            </div>
          </div>
        </section>

        <section className="panel alert-panel">
          <div className="panel-header">
            <h2>Alerts</h2>
            <button className="secondary" onClick={() => startDictation("alert")} disabled={!canDictate}>
              {speech.listening && voiceTarget === "alert" ? "Listening..." : canDictate ? "Speak rule" : "Mic unavailable"}
            </button>
          </div>
          <div className="composer compact">
            <textarea
              value={alertText}
              onChange={(e) => setAlertText(e.target.value)}
              placeholder="Notify me when someone enters"
            />
            <div className="actions">
              <button className="secondary" onClick={() => setAlertText("")}>
                Clear
              </button>
              <button onClick={handleCreateAlert} disabled={busy}>
                Create alert
              </button>
            </div>
          </div>

          <div className="alert-columns">
            <div>
              <h3>Rules</h3>
              <div className="stack">
                {alerts.rules.length === 0 ? (
                  <EmptyState title="No rules yet" description="Create a rule by typing or speaking an alert condition." />
                ) : (
                  alerts.rules.map((rule: AlertRule) => (
                    <div className="mini-card" key={rule.id}>
                      <p>{rule.text}</p>
                      <div className="tag-row">
                        {rule.object_keywords.map((keyword) => (
                          <span className="tag" key={keyword}>
                            {keyword}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div>
              <h3>Hits</h3>
              <div className="stack">
                {alerts.hits.length === 0 ? (
                  <EmptyState title="No hits yet" description="Alert hits will show here during processing." />
                ) : (
                  alerts.hits.map((hit: AlertHit) => (
                    <div className="mini-card hit" key={hit.id}>
                      <p>{hit.message}</p>
                      <span className="mono">{formatTimestamp(hit.timestamp_iso)}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  );
}

function formatSeconds(value: number) {
  if (!Number.isFinite(value)) return "0s";
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}m ${seconds}s`;
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
;
}
ite(value)) return "0s";
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}m ${seconds}s`;
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
