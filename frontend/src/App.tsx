import {
  Activity,
  Bell,
  Camera,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  FileVideo,
  Map,
  Play,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  Upload
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

type Severity = "High" | "Medium" | "Low";
type LoadState = "idle" | "loading" | "ready" | "error";

type CameraConfig = {
  id: string;
  name: string;
  source_type: string;
  source_path: string;
  reference_resolution: [number, number];
  timezone: string;
};

type ZoneConfig = {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
};

type RuleConfig = {
  id: string;
  name: string;
  enabled: boolean;
};

type RoadLensConfig = {
  camera: CameraConfig;
  zones: ZoneConfig[];
};

type RulesResponse = {
  rules: RuleConfig[];
};

type EvidenceDetection = {
  id: number;
  plate_text: string;
  detector_confidence: number | null;
  ocr_confidence: number | null;
};

type EvidenceItem = {
  id: number;
  rule: {
    name: string;
  };
  zone: {
    name: string;
    type: string;
  };
  source_frame_number: number;
  timestamp_seconds: number | null;
  vehicle: {
    class: string;
    confidence: number | null;
  };
  review_status: string;
  detections: EvidenceDetection[];
  artifacts: Array<{
    id: number;
    type: string;
    url: string;
  }>;
};

type EvidenceResponse = {
  count: number;
  items: EvidenceItem[];
};

type ApiSnapshot = {
  config: RoadLensConfig | null;
  rules: RuleConfig[];
  evidence: EvidenceItem[];
};

const emptySnapshot: ApiSnapshot = {
  config: null,
  rules: [],
  evidence: []
};

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function fetchDashboardSnapshot(): Promise<ApiSnapshot> {
  await apiGet<{ status: string }>("/api/health");
  const [config, rulesResponse, evidenceResponse] = await Promise.all([
    apiGet<RoadLensConfig>("/api/config"),
    apiGet<RulesResponse>("/api/rules"),
    apiGet<EvidenceResponse>("/api/evidence")
  ]);

  return {
    config,
    rules: rulesResponse.rules,
    evidence: evidenceResponse.items
  };
}

function App() {
  const [snapshot, setSnapshot] = useState<ApiSnapshot>(emptySnapshot);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadDashboard = useCallback(
    async (isCancelled: () => boolean = () => false) => {
      setLoadState("loading");
      setErrorMessage(null);

      try {
        const nextSnapshot = await fetchDashboardSnapshot();

        if (isCancelled()) {
          return;
        }

        setSnapshot(nextSnapshot);
        setLoadState("ready");
      } catch (error) {
        if (isCancelled()) {
          return;
        }

        setSnapshot(emptySnapshot);
        setErrorMessage(error instanceof Error ? error.message : "API unavailable");
        setLoadState("error");
      }
    },
    []
  );

  useEffect(() => {
    let cancelled = false;

    void loadDashboard(() => cancelled);

    return () => {
      cancelled = true;
    };
  }, [loadDashboard]);

  const activeRules = snapshot.rules.filter((rule) => rule.enabled);
  const enabledZones = snapshot.config?.zones.filter((zone) => zone.enabled) ?? [];
  const openReviews = snapshot.evidence.filter(
    (item) => item.review_status === "pending"
  );
  const acceptedReviews = snapshot.evidence.filter(
    (item) => item.review_status === "accepted"
  );
  const sourceRows = useMemo(() => {
    if (!snapshot.config) {
      return [];
    }

    const [width, height] = snapshot.config.camera.reference_resolution;
    return [
      {
        label: "Source",
        value: snapshot.config.camera.source_path
      },
      {
        label: "Type",
        value: snapshot.config.camera.source_type
      },
      {
        label: "Resolution",
        value: `${width} x ${height}`
      },
      {
        label: "Timezone",
        value: snapshot.config.camera.timezone
      }
    ];
  }, [snapshot.config]);

  const cameraRows = useMemo(() => {
    if (!snapshot.config) {
      return [];
    }

    return [
      {
        name: snapshot.config.camera.name,
        location: snapshot.config.camera.source_path,
        status: loadState === "ready" ? "Configured" : "Unknown",
        fps: snapshot.config.camera.source_type,
        activeRules: activeRules.length
      }
    ];
  }, [activeRules.length, loadState, snapshot.config]);

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark">
            <Camera aria-hidden="true" size={20} />
          </span>
          <div>
            <strong>RoadLens</strong>
            <span>Traffic evidence ops</span>
          </div>
        </div>

        <nav className="nav-list">
          <a className="nav-item active" href="#overview">
            <CircleGauge size={18} aria-hidden="true" />
            Overview
          </a>
          <a className="nav-item" href="#review">
            <ShieldCheck size={18} aria-hidden="true" />
            Evidence
          </a>
          <a className="nav-item" href="#zones">
            <Map size={18} aria-hidden="true" />
            Zones
          </a>
          <a className="nav-item" href="#rules">
            <SlidersHorizontal size={18} aria-hidden="true" />
            Rules
          </a>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Live operations</p>
            <h1>Evidence pipeline</h1>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" aria-label="Notifications">
              <Bell size={18} aria-hidden="true" />
            </button>
            <button className="button secondary" disabled>
              <Upload size={18} aria-hidden="true" />
              Upload video
            </button>
            <button className="button primary" disabled>
              <Play size={18} aria-hidden="true" />
              Start job
            </button>
          </div>
        </header>

        <ApiStatusBanner state={loadState} message={errorMessage} />

        <section className="metrics-grid" aria-label="System metrics">
          <MetricCard
            icon={<Activity size={20} aria-hidden="true" />}
            label="Configured cameras"
            value={snapshot.config ? "1" : "0"}
            detail={snapshot.config?.camera.name ?? "Backend data pending"}
          />
          <MetricCard
            icon={<FileVideo size={20} aria-hidden="true" />}
            label="Evidence records"
            value={String(snapshot.evidence.length)}
            detail={`${openReviews.length} pending review`}
          />
          <MetricCard
            icon={<TriangleAlert size={20} aria-hidden="true" />}
            label="Active rules"
            value={String(activeRules.length)}
            detail={`${enabledZones.length} enabled zones`}
          />
          <MetricCard
            icon={<CheckCircle2 size={20} aria-hidden="true" />}
            label="Accepted"
            value={String(acceptedReviews.length)}
            detail="From persisted evidence"
          />
        </section>

        <div className="content-grid">
          <section className="panel" id="overview">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Cameras</p>
                <h2>Field sources</h2>
              </div>
              <button className="text-button">
                Manage
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>

            <div className="camera-list">
              {cameraRows.length > 0 ? (
                cameraRows.map((camera) => (
                  <article className="camera-row" key={camera.name}>
                    <div className="camera-icon">
                      <Camera size={20} aria-hidden="true" />
                    </div>
                    <div>
                      <h3>{camera.name}</h3>
                      <p>{camera.location}</p>
                    </div>
                    <dl>
                      <div>
                        <dt>Status</dt>
                        <dd>{camera.status}</dd>
                      </div>
                      <div>
                        <dt>Source</dt>
                        <dd>{camera.fps}</dd>
                      </div>
                      <div>
                        <dt>Rules</dt>
                        <dd>{camera.activeRules}</dd>
                      </div>
                    </dl>
                  </article>
                ))
              ) : (
                <EmptyState title="No camera config loaded" />
              )}
            </div>
          </section>

          <section className="panel" id="source">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Input</p>
                <h2>Configured source</h2>
              </div>
              <FileVideo size={18} aria-hidden="true" />
            </div>

            <div className="source-list">
              {sourceRows.length > 0 ? (
                sourceRows.map((row) => (
                  <div className="source-row" key={row.label}>
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                ))
              ) : (
                <EmptyState title="No configured source loaded" />
              )}
            </div>
          </section>
        </div>

        <div className="content-grid lower-grid">
          <section className="panel" id="review">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Review</p>
                <h2>Violation evidence</h2>
              </div>
              <button className="text-button">
                Open queue
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>

            {snapshot.evidence.length > 0 ? (
              <div
                className="violation-table"
                role="table"
                aria-label="Violation queue"
              >
                <div className="table-head" role="row">
                  <span role="columnheader">Plate</span>
                  <span role="columnheader">Rule</span>
                  <span role="columnheader">Zone</span>
                  <span role="columnheader">Frame</span>
                  <span role="columnheader">Status</span>
                </div>
                {snapshot.evidence.map((violation) => (
                  <div className="table-row" role="row" key={violation.id}>
                    <strong role="cell">{plateLabel(violation)}</strong>
                    <span role="cell">{violation.rule.name}</span>
                    <span role="cell">{violation.zone.name}</span>
                    <span role="cell">{violation.source_frame_number}</span>
                    <span role="cell">
                      <SeverityBadge severity={severityFor(violation)} />
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No persisted evidence records" />
            )}
          </section>

          <section className="panel" id="rules">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Configuration</p>
                <h2>Active rules</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Refresh dashboard"
                onClick={() => void loadDashboard()}
              >
                <RefreshCw size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="rule-list">
              {snapshot.rules.length > 0 ? (
                snapshot.rules.map((rule) => (
                  <label className="rule-row" key={rule.id}>
                    <input type="checkbox" checked={rule.enabled} readOnly />
                    <span>{rule.name}</span>
                  </label>
                ))
              ) : (
                <EmptyState title="No rules configured" />
              )}
            </div>

            <div className="zone-summary" id="zones">
              <Map size={20} aria-hidden="true" />
              <div>
                <strong>{enabledZones.length} enabled zones</strong>
                <span>{zoneSummary(enabledZones)}</span>
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function ApiStatusBanner({
  state,
  message
}: {
  state: LoadState;
  message: string | null;
}) {
  if (state === "ready") {
    return null;
  }

  const text =
    state === "loading"
      ? "Loading backend data..."
      : message
        ? `Backend unavailable: ${message}`
        : "Backend data is not loaded.";

  return <div className={`api-banner api-banner-${state}`}>{text}</div>;
}

function EmptyState({ title }: { title: string }) {
  return <div className="empty-state">{title}</div>;
}

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`badge severity-${severity.toLowerCase()}`}>{severity}</span>
  );
}

function plateLabel(item: EvidenceItem) {
  const firstDetection = item.detections[0];
  if (!firstDetection) {
    return "OCR review";
  }

  return firstDetection.plate_text;
}

function severityFor(item: EvidenceItem): Severity {
  if (item.review_status === "accepted") {
    return "Low";
  }

  const confidence = item.detections[0]?.ocr_confidence ?? 0;
  if (confidence < 0.7) {
    return "High";
  }

  return "Medium";
}

function zoneSummary(zones: ZoneConfig[]) {
  if (zones.length === 0) {
    return "No active zones from the loaded config";
  }

  return zones.map((zone) => zone.name).join(", ");
}

export default App;
