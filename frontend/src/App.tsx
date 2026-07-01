import {
  Activity,
  Bell,
  Camera,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  Clock3,
  FileVideo,
  Map,
  Play,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  Upload
} from "lucide-react";
import type { ReactNode } from "react";

type JobStatus = "Running" | "Review" | "Queued";
type Severity = "High" | "Medium" | "Low";

const cameras = [
  {
    name: "Demo Intersection 01",
    location: "Kathmandu Ring Road",
    status: "Online",
    fps: "24 fps",
    activeRules: 2
  },
  {
    name: "North Gate Camera",
    location: "School Zone",
    status: "Idle",
    fps: "0 fps",
    activeRules: 1
  }
];

const jobs: Array<{
  id: string;
  source: string;
  status: JobStatus;
  progress: number;
  detections: number;
}> = [
  {
    id: "JOB-1042",
    source: "test_video.mp4",
    status: "Running",
    progress: 68,
    detections: 12
  },
  {
    id: "JOB-1041",
    source: "crosswalk_evening.mp4",
    status: "Review",
    progress: 100,
    detections: 8
  },
  {
    id: "JOB-1040",
    source: "restricted_lane.mp4",
    status: "Queued",
    progress: 0,
    detections: 0
  }
];

const violations: Array<{
  plate: string;
  rule: string;
  camera: string;
  time: string;
  severity: Severity;
}> = [
  {
    plate: "BA 19 PA 8742",
    rule: "Restricted Zone Entry",
    camera: "Demo Intersection 01",
    time: "09:42",
    severity: "High"
  },
  {
    plate: "PROBABLE: GA 12 CHA 3011",
    rule: "Red Light Stop-Line",
    camera: "Demo Intersection 01",
    time: "09:31",
    severity: "Medium"
  },
  {
    plate: "OCR REVIEW",
    rule: "Zebra Crossing Encroachment",
    camera: "North Gate Camera",
    time: "08:58",
    severity: "Low"
  }
];

const rules = [
  "Restricted zone entry",
  "Red-light stop-line violation",
  "Zebra crossing encroachment"
];

function App() {
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
            <button className="button secondary">
              <Upload size={18} aria-hidden="true" />
              Upload video
            </button>
            <button className="button primary">
              <Play size={18} aria-hidden="true" />
              Start job
            </button>
          </div>
        </header>

        <section className="metrics-grid" aria-label="System metrics">
          <MetricCard
            icon={<Activity size={20} aria-hidden="true" />}
            label="Active cameras"
            value="2"
            detail="1 live, 1 idle"
          />
          <MetricCard
            icon={<FileVideo size={20} aria-hidden="true" />}
            label="Processing jobs"
            value="3"
            detail="1 running"
          />
          <MetricCard
            icon={<TriangleAlert size={20} aria-hidden="true" />}
            label="Open reviews"
            value="18"
            detail="5 high priority"
          />
          <MetricCard
            icon={<CheckCircle2 size={20} aria-hidden="true" />}
            label="Accepted today"
            value="42"
            detail="96% confidence median"
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
              {cameras.map((camera) => (
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
                      <dt>Rate</dt>
                      <dd>{camera.fps}</dd>
                    </div>
                    <div>
                      <dt>Rules</dt>
                      <dd>{camera.activeRules}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          </section>

          <section className="panel" id="jobs">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Queue</p>
                <h2>Processing jobs</h2>
              </div>
              <Clock3 size={18} aria-hidden="true" />
            </div>

            <div className="job-list">
              {jobs.map((job) => (
                <article className="job-row" key={job.id}>
                  <div className="job-title">
                    <strong>{job.id}</strong>
                    <span>{job.source}</span>
                  </div>
                  <StatusBadge status={job.status} />
                  <div className="progress" aria-label={`${job.progress}% complete`}>
                    <span style={{ width: `${job.progress}%` }} />
                  </div>
                  <span className="job-count">{job.detections} detections</span>
                </article>
              ))}
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

            <div className="violation-table" role="table" aria-label="Violation queue">
              <div className="table-head" role="row">
                <span role="columnheader">Plate</span>
                <span role="columnheader">Rule</span>
                <span role="columnheader">Camera</span>
                <span role="columnheader">Time</span>
                <span role="columnheader">Priority</span>
              </div>
              {violations.map((violation) => (
                <div className="table-row" role="row" key={`${violation.plate}-${violation.time}`}>
                  <strong role="cell">{violation.plate}</strong>
                  <span role="cell">{violation.rule}</span>
                  <span role="cell">{violation.camera}</span>
                  <span role="cell">{violation.time}</span>
                  <span role="cell">
                    <SeverityBadge severity={violation.severity} />
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel" id="rules">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Configuration</p>
                <h2>Active rules</h2>
              </div>
              <button className="icon-button" aria-label="Rule settings">
                <SlidersHorizontal size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="rule-list">
              {rules.map((rule) => (
                <label className="rule-row" key={rule}>
                  <input type="checkbox" defaultChecked />
                  <span>{rule}</span>
                </label>
              ))}
            </div>

            <div className="zone-summary" id="zones">
              <Map size={20} aria-hidden="true" />
              <div>
                <strong>4 calibrated zones</strong>
                <span>Detection ROI, stop line, restricted lane, crossing</span>
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

function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{status}</span>;
}

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`badge severity-${severity.toLowerCase()}`}>{severity}</span>
  );
}

export default App;
