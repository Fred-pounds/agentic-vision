import { useEffect, useMemo, useRef, useState } from "react";
import {
  askQuery,
  clearAlertHits,
  createAlert,
  deleteAlertRule,
  getAlerts,
  getVideoStatus,
  listEvents,
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
    { role: "assistant", text: "Welcome. Upload a surveillance or event video to begin analysis." },
  ]);
  const [query, setQuery] = useState("");
  const [alertText, setAlertText] = useState("");
  const [location, setLocation] = useState("Main Office");
  const [recordingStart, setRecordingStart] = useState(new Date().toISOString().split(".")[0]);
  const [busy, setBusy] = useState(false);
  const [voiceTarget, setVoiceTarget] = useState<DictationTarget>("query");
  const [speechEnabled, setSpeechEnabled] = useState(false);
  const [notificationPermission, setNotificationPermission] = useState(Notification.permission);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const pollingRef = useRef<number | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const timelineTopRef = useRef<HTMLDivElement | null>(null);
  const lastHitIdRef = useRef<string | null>(null);
  const speech = useSpeechRecognition();
  const canDictate = speech.supported;
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const requestNotificationPermission = async () => {
    const permission = await Notification.requestPermission();
    setNotificationPermission(permission);
  };

  const notifyUser = (hit: AlertHit) => {
    if (notificationPermission === "granted") {
      new Notification("Agentic Vision Alert", {
        body: hit.message,
        icon: "/favicon.png",
      });
    }
  };

  const streaming = useMemo(() => {
    if (!status) return false;
    return status.status === "queued" || status.status === "processing";
  }, [status]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  useEffect(() => {
    if (streaming && events.length > 0) {
      timelineTopRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events.length, streaming]);

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
        
        // Trigger notification for new hits
        if (nextAlerts.hits.length > 0) {
          const latestHit = nextAlerts.hits[0];
          if (latestHit.id !== lastHitIdRef.current) {
            notifyUser(latestHit);
            lastHitIdRef.current = latestHit.id;
          }
        }
        
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
  }, [video, notificationPermission]);

  useEffect(() => {
    if (!speech.transcript) return;
    if (voiceTarget === "query") {
      setQuery(speech.transcript);
    } else {
      setAlertText(speech.transcript);
    }
  }, [speech.transcript, voiceTarget]);

  async function refreshAlerts() {
    try {
      const nextAlerts = await getAlerts();
      setAlerts(nextAlerts);
      if (nextAlerts.hits.length > 0) {
        lastHitIdRef.current = nextAlerts.hits[0].id;
      }
    } catch {
      // Backend may be starting up
    }
  }

  async function handleDeleteRule(ruleId: string) {
    if (confirm("Are you sure you want to remove this monitoring rule?")) {
      await deleteAlertRule(ruleId);
      await refreshAlerts();
    }
  }

  async function handleClearHits() {
    if (confirm("This will permanently delete all recorded incidents. Continue?")) {
      await clearAlertHits();
      await refreshAlerts();
    }
  }

  function handleExportLogs() {
    if (alerts.hits.length === 0) return;

    // Create CSV content for non-technical users (Excel compatible)
    const headers = ["Timestamp", "Location", "Alert Message"];
    const rows = alerts.hits.map(hit => [
      `"${formatTimestamp(hit.timestamp_iso)}"`,
      `"${location}"`,
      `"${hit.message.replace(/"/g, '""')}"`
    ]);

    const csvContent = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `security-report-${new Date().toLocaleDateString().replace(/\//g, '-')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
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
      setChat((prev) => [
        ...prev,
        { role: "assistant", text: `Processing ${file.name}. The intelligence engine is now analyzing the stream.` }
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function handleQuery() {
    const question = query.trim();
    if (!question || busy) return;
    
    setBusy(true);
    setQuery(""); // Clear immediately for better UX
    setChat((prev) => [...prev, { role: "user", text: question }]);
    
    try {
      const response = await askQuery(question, video?.id);
      appendAnswer(response);
      if (speechEnabled) speak(response.answer);
    } catch (error) {
      console.error("Query failed:", error);
      setChat((prev) => [
        ...prev,
        { 
          role: "assistant", 
          text: "I'm sorry, I encountered an error while processing your request. Please ensure the backend and GPU are active and try again." 
        }
      ]);
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

  function appendAnswer(response: QueryResult) {
    setChat((prev) => [
      ...prev,
      { role: "assistant", text: response.answer, fallback: response.used_fallback, events: response.supporting_events },
    ]);
    if (response.supporting_events.length > 0) {
      seekTo(response.supporting_events[0].timestamp_seconds);
    }
  }

  function seekTo(seconds: number) {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      videoRef.current.pause();
    }
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
          <p className="eyebrow">Enterprise Vision Intelligence</p>
          <h1>Intelligent Video Monitoring & Automated Analysis</h1>
        </div>
        <div className={`status-pill ${streaming ? "live" : ""}`}>
          {streaming ? "System Analysis Active" : "System Idle"}
        </div>
      </header>

      <main className="grid">
        <section className="panel hero-panel">
          <div className="panel-header">
            <h2>1. Video Source</h2>
          </div>
          <p className="panel-desc">Upload a video file to begin automated security analysis.</p>
          
          {video?.video_url && (
            <div className="video-preview">
              <video 
                ref={videoRef}
                src={`${import.meta.env.VITE_API_URL || "http://localhost:8000"}${video.video_url}`}
                controls
                className="main-video"
              />
            </div>
          )}

          <div className="upload-card">
            <div className="file-input-wrapper">
              <input ref={fileInput} type="file" accept="video/*" className="custom-file-input" />
            </div>
            <div className="field-row">
              <label title="Where was this video recorded?">
                Area Name
                <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Front Desk" />
              </label>
              <label title="When did this recording start?">
                Recording Time
                <input
                  value={recordingStart}
                  onChange={(e) => setRecordingStart(e.target.value)}
                  placeholder="YYYY-MM-DD HH:MM"
                />
              </label>
            </div>
            <button onClick={handleUpload} disabled={busy}>
              {busy ? "Analyzing Video..." : "Start Analysis"}
            </button>
          </div>

          <div className="progress-block">
            <div className="progress-meta">
              <span>Analysis Progress</span>
              <span>{status ? `${Math.round(status.progress * 100)}% Complete` : "Ready"}</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${Math.max(2, Math.round((status?.progress ?? 0) * 100))}%` }} />
            </div>
            <div className="status-grid">
              <Metric label="Current File" value={video?.filename ?? "None"} />
              <Metric label="Items Found" value={String(status?.event_count ?? 0)} />
              <Metric label="Alerts Triggered" value={String(status?.alert_count ?? 0)} />
              <Metric label="Analyzed Time" value={formatSeconds(status?.current_time_seconds ?? 0)} />
            </div>
            {status?.error ? <p className="error-copy">Error: {status.error}</p> : null}
          </div>
        </section>

        <section className="panel timeline-panel">
          <div className="panel-header">
            <h2>2. Activity Log</h2>
            <span className="subtle">{visibleEvents.length} items detected</span>
          </div>
          <p className="panel-desc">A list of everything the system has identified. Click any item to watch that moment.</p>
          <div className="timeline-list">
            <div ref={timelineTopRef} />
            {visibleEvents.length === 0 ? (
              <EmptyState title="Awaiting Data" description="Upload a video to see the activity timeline appear here." />
            ) : (
              visibleEvents.map((event) => (
                <article 
                  className="event-card clickable" 
                  key={event.id} 
                  onClick={() => seekTo(event.timestamp_seconds)}
                >
                  <div className="event-topline">
                    <strong>{formatTimestamp(event.timestamp_iso)}</strong>
                    <span className="location-tag">{event.location}</span>
                  </div>
                  <p className="event-caption">{event.caption}</p>
                  <div className="tag-row">
                    {event.objects.map((object) => (
                      <span className="tag" key={object}>
                        {object}
                      </span>
                    ))}
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="panel chat-panel">
          <div className="panel-header">
            <h2>3. Search & Ask</h2>
            <div className="toggle-row">
              <button className="secondary small" onClick={() => setSpeechEnabled((value) => !value)}>
                Voice Response: {speechEnabled ? "ON" : "OFF"}
              </button>
            </div>
          </div>
          <p className="panel-desc">Type or speak naturally to find specific moments (e.g., "When did the white car park?").</p>

          <div className="chat-log">
            {chat.map((message, index) => (
              <div className={`bubble ${message.role}`} key={`${message.role}-${index}`}>
                <p>{message.text}</p>
                {message.fallback ? <span className="pill warn">Estimated Answer</span> : null}
                {message.events?.length ? (
                  <div className="supporting-events">
                    {message.events.slice(0, 3).map((event) => (
                      <span className="tag subtle-tag" key={event.id} onClick={() => seekTo(event.timestamp_seconds)}>
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
            <textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type your question here..." />
            <div className="actions">
              <button className="secondary" onClick={() => startDictation("query")} disabled={!canDictate}>
                {speech.listening && voiceTarget === "query" ? "Listening..." : canDictate ? "Speak Question" : "Microphone Restricted"}
              </button>
              <button onClick={handleQuery} disabled={busy}>
                Ask System
              </button>
            </div>
          </div>
        </section>

        <section className="panel alert-panel">
          <div className="panel-header">
            <h2>4. Automated Monitoring</h2>
            <div className="panel-actions">
              {notificationPermission !== "granted" && (
                <button className="secondary small" onClick={requestNotificationPermission} title="Receive alerts on your computer even when away from this page">
                  🔔 Enable Notifications
                </button>
              )}
              <button className="secondary small" onClick={handleClearHits} disabled={alerts.hits.length === 0}>
                Clear All Logs
              </button>
              <button className="secondary small" onClick={handleExportLogs} disabled={alerts.hits.length === 0} title="Download a report for Excel or Google Sheets">
                Download Report (CSV)
              </button>
            </div>
          </div>
          <p className="panel-desc">Tell the system what to look for, and it will notify you the instant it happens.</p>
          <div className="composer compact">
            <textarea
              value={alertText}
              onChange={(e) => setAlertText(e.target.value)}
              placeholder="e.g. 'Alert me if a dog enters the area' or 'Notify me when someone arrives'"
            />
            <div className="actions">
              <button className="secondary" onClick={() => startDictation("alert")} disabled={!canDictate}>
                {speech.listening && voiceTarget === "alert" ? "Listening..." : canDictate ? "Speak Instruction" : "Microphone Restricted"}
              </button>
              <button onClick={handleCreateAlert} disabled={busy}>
                Add Alert Rule
              </button>
            </div>
          </div>

          <div className="alert-columns">
            <div>
              <h3>Monitoring Rules</h3>
              <div className="stack">
                {alerts.rules.length === 0 ? (
                  <EmptyState title="No active rules" description="Use the box above to tell the system what events to watch for." />
                ) : (
                  alerts.rules.map((rule: AlertRule) => (
                    <div className="mini-card policy-card" key={rule.id}>
                      <div className="card-row">
                        <p>{rule.text}</p>
                        <button className="text-btn danger" onClick={() => handleDeleteRule(rule.id)}>Remove</button>
                      </div>
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
              <h3>Recent Incidents</h3>
              <div className="stack">
                {alerts.hits.length === 0 ? (
                  <EmptyState title="All systems clear" description="Matches against your rules will appear here as they happen." />
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
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
}
