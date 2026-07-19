import {
  AlertCircle,
  Building2,
  Camera,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  FileVideo,
  Gauge,
  LayoutDashboard,
  LogOut,
  Mail,
  Map,
  Play,
  Plus,
  RefreshCw,
  ScanLine,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  Trash2,
  Users,
  Warehouse
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode
} from "react";

import { Button } from "./components/ui/button";
import { Card } from "./components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle
} from "./components/ui/dialog";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "./components/ui/select";
import { Switch } from "./components/ui/switch";
import "./dashboard.css";
import {
  productApi,
  type CameraSummary,
  type UserSummary,
  type WorkspaceSummary
} from "./ProductApp";

type LoadState = "idle" | "loading" | "ready" | "error";

type ProcessingJob = {
  id: number;
  workspace_id: number;
  camera_id: number;
  job_type: string;
  status:
    | "queued"
    | "running"
    | "cancel_requested"
    | "canceled"
    | "completed"
    | "failed";
  progress: {
    event?: string;
    message?: string;
    frame_index?: number;
    total_frames?: number;
    detection_count?: number;
  } | null;
  error: string | null;
  result: { detection_count?: number } | null;
  claimed_by: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

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
  points_normalized: Array<[number, number]>;
};

type RuleConfig = {
  id: string;
  name: string;
  enabled: boolean;
  actions: string[];
};

type RoadLensConfig = {
  camera: CameraConfig;
  zones: ZoneConfig[];
  rules: RuleConfig[];
  models: {
    vehicle_detector: string;
    plate_detector: string;
    ocr_engine: string;
  };
  frame_selection: {
    motion_threshold: number;
    cooldown_frames: number;
    score_method: string;
  };
  detection: {
    vehicle_confidence: number;
    plate_confidence: number;
  };
  storage: {
    save_to_db: boolean;
    save_evidence_images: boolean;
  };
};

type EvidenceDetection = {
  id: number;
  plate_text: string;
  detector_confidence: number | null;
  ocr_confidence: number | null;
};

type EvidenceArtifact = {
  id: number;
  type: string;
  url: string;
  width: number | null;
  height: number | null;
};

type EvidenceItem = {
  id: number;
  rule: {
    id: string;
    name: string;
  };
  zone: {
    id: string;
    name: string;
    type: string;
  };
  event_type: string;
  source_frame_number: number;
  timestamp_seconds: number | null;
  vehicle: {
    class: string;
    confidence: number | null;
  };
  review_status: string;
  created_at: string;
  detections: EvidenceDetection[];
  artifacts: EvidenceArtifact[];
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

type PageId =
  | "overview"
  | "evidence"
  | "cameras"
  | "zones"
  | "rules"
  | "workspace"
  | "team";

const pageMeta: Record<PageId, { title: string; description: string }> = {
  overview: {
    title: "Operations overview",
    description:
      "Monitor camera readiness, rule coverage, zones, and the evidence queue."
  },
  evidence: {
    title: "Evidence",
    description:
      "Review persisted violation events, plates, source frames, and decisions."
  },
  cameras: {
    title: "Cameras",
    description:
      "Add and manage live streams, webcams, and uploaded video sources."
  },
  zones: {
    title: "Zones",
    description:
      "Configure the normalized geometry used to evaluate traffic events."
  },
  rules: {
    title: "Rules",
    description:
      "Review enabled enforcement rules and the actions each event triggers."
  },
  workspace: {
    title: "Workspace",
    description:
      "Manage workspace identity, timezone, and create additional operations spaces."
  },
  team: {
    title: "Team",
    description:
      "Add users and control their access with workspace-level roles."
  }
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

async function fetchDashboardSnapshot(
  workspaceId: number,
  cameraId: number | null
): Promise<ApiSnapshot> {
  await apiGet<{ status: string }>("/api/health");
  const evidencePath = `/api/workspaces/${workspaceId}/evidence${
    cameraId == null ? "" : `?camera_id=${cameraId}`
  }`;
  const evidenceResponse = await apiGet<EvidenceResponse>(evidencePath);
  if (cameraId == null) {
    return { config: null, rules: [], evidence: evidenceResponse.items };
  }
  const cameraResponse = await apiGet<{ config: RoadLensConfig }>(
    `/api/workspaces/${workspaceId}/cameras/${cameraId}`
  );

  return {
    config: cameraResponse.config,
    rules: cameraResponse.config.rules,
    evidence: evidenceResponse.items
  };
}

function Dashboard({
  user,
  workspaces,
  activeWorkspace,
  cameras,
  activeCamera,
  onWorkspaceChange,
  onCameraChange,
  onProductChange,
  onLogout
}: {
  user: UserSummary;
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary | null;
  cameras: CameraSummary[];
  activeCamera: CameraSummary | null;
  onWorkspaceChange: (workspaceId: number) => void;
  onCameraChange: (cameraId: number) => void;
  onProductChange: () => Promise<void>;
  onLogout: () => Promise<void>;
}) {
  const [snapshot, setSnapshot] = useState<ApiSnapshot>(emptySnapshot);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(
    null
  );
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [activePage, setActivePage] = useState<PageId>(() =>
    pageFromPath(window.location.pathname)
  );

  const loadDashboard = useCallback(
    async (isCancelled: () => boolean = () => false) => {
      if (activeWorkspace == null) {
        setSnapshot(emptySnapshot);
        setLoadState("ready");
        return;
      }
      setLoadState("loading");
      setErrorMessage(null);

      try {
        const nextSnapshot = await fetchDashboardSnapshot(
          activeWorkspace.id,
          activeCamera?.id ?? null
        );
        if (isCancelled()) {
          return;
        }

        setSnapshot(nextSnapshot);
        setLastSyncedAt(new Date());
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
    [activeCamera?.id, activeWorkspace]
  );

  useEffect(() => {
    let cancelled = false;
    void loadDashboard(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [loadDashboard]);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "SELECT" ||
        target?.isContentEditable;

      if (event.key === "/" && !isTyping) {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
    };

    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  useEffect(() => {
    const handlePopState = () => setActivePage(pageFromPath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const activeRules = snapshot.rules.filter((rule) => rule.enabled);
  const enabledZones = snapshot.config?.zones.filter((zone) => zone.enabled) ?? [];
  const pendingEvidence = snapshot.evidence.filter(
    (item) => item.review_status === "pending"
  );

  const filteredEvidence = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) {
      return snapshot.evidence;
    }

    return snapshot.evidence.filter((item) => {
      const plate = item.detections[0]?.plate_text ?? "";
      return [plate, item.rule.name, item.zone.name, item.review_status].some(
        (value) => value.toLocaleLowerCase().includes(query)
      );
    });
  }, [searchQuery, snapshot.evidence]);

  const openEvidence = (item: EvidenceItem) => {
    setSelectedEvidence(item);
  };

  const closeEvidence = () => {
    setSelectedEvidence(null);
  };

  const navigate = (
    event: ReactMouseEvent<HTMLAnchorElement>,
    page: PageId
  ) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }

    event.preventDefault();
    const nextPath = `/${page}`;
    if (window.location.pathname !== nextPath) {
      window.history.pushState({}, "", nextPath);
      setActivePage(page);
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  };

  const meta = pageMeta[activePage];

  return (
    <div className="roadlens-shell">
      <Sidebar
        user={user}
        workspaces={workspaces}
        activeWorkspace={activeWorkspace}
        cameras={cameras}
        activeCamera={activeCamera}
        loadState={loadState}
        activePage={activePage}
        onNavigate={navigate}
        onWorkspaceChange={onWorkspaceChange}
        onCameraChange={onCameraChange}
        onLogout={onLogout}
      />

      <main className="dashboard-main">
        <header className="dashboard-header">
          <div className="heading-block">
            <div className="breadcrumb">
              <span>RoadLens</span>
              <ChevronRight size={14} aria-hidden="true" />
              <span>{humanize(activePage)}</span>
            </div>
            <h1>{meta.title}</h1>
            <p>{meta.description}</p>
          </div>

          <div className="header-actions">
            {activePage === "evidence" ? (
              <label className="search-field">
                <Search size={16} aria-hidden="true" />
                <span className="sr-only">Search evidence</span>
                <input
                  ref={searchInputRef}
                  type="search"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search evidence"
                />
                <kbd>/</kbd>
              </label>
            ) : null}
            <Button
              type="button"
              data-state={loadState === "loading" ? "loading" : undefined}
              disabled={loadState === "loading"}
              onClick={() => void loadDashboard()}
            >
              <RefreshCw size={16} aria-hidden="true" />
              <span>{loadState === "loading" ? "Refreshing" : "Refresh"}</span>
            </Button>
          </div>
        </header>

        <StatusLine
          state={loadState}
          message={errorMessage}
          cameraName={snapshot.config?.camera.name}
          lastSyncedAt={lastSyncedAt}
        />

        {loadState === "loading" && !snapshot.config ? (
          <DashboardSkeleton />
        ) : (
          <PageContent
            page={activePage}
            snapshot={snapshot}
            activeRules={activeRules}
            enabledZones={enabledZones}
            pendingEvidence={pendingEvidence}
            filteredEvidence={filteredEvidence}
            searchQuery={searchQuery}
            onClearSearch={() => setSearchQuery("")}
            onOpenEvidence={openEvidence}
            onRefresh={() => void loadDashboard()}
            onNavigate={navigate}
            user={user}
            workspaces={workspaces}
            activeWorkspace={activeWorkspace}
            cameras={cameras}
            activeCamera={activeCamera}
            onWorkspaceChange={onWorkspaceChange}
            onCameraChange={onCameraChange}
            onProductChange={onProductChange}
          />
        )}
      </main>

      <EvidenceDialog
        evidence={selectedEvidence}
        onClose={closeEvidence}
      />
    </div>
  );
}

function PageContent({
  page,
  snapshot,
  activeRules,
  enabledZones,
  pendingEvidence,
  filteredEvidence,
  searchQuery,
  onClearSearch,
  onOpenEvidence,
  onRefresh,
  onNavigate,
  user,
  workspaces,
  activeWorkspace,
  cameras,
  activeCamera,
  onWorkspaceChange,
  onCameraChange,
  onProductChange
}: {
  page: PageId;
  snapshot: ApiSnapshot;
  activeRules: RuleConfig[];
  enabledZones: ZoneConfig[];
  pendingEvidence: EvidenceItem[];
  filteredEvidence: EvidenceItem[];
  searchQuery: string;
  onClearSearch: () => void;
  onOpenEvidence: (item: EvidenceItem) => void;
  onRefresh: () => void;
  onNavigate: (
    event: ReactMouseEvent<HTMLAnchorElement>,
    page: PageId
  ) => void;
  user: UserSummary;
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary | null;
  cameras: CameraSummary[];
  activeCamera: CameraSummary | null;
  onWorkspaceChange: (workspaceId: number) => void;
  onCameraChange: (cameraId: number) => void;
  onProductChange: () => Promise<void>;
}) {
  const snapshotUrl =
    activeWorkspace && activeCamera
      ? cameraSnapshotUrl(activeWorkspace.id, activeCamera.id, activeCamera.updated_at)
      : undefined;

  if (page === "evidence") {
    return (
      <section className="surface page-surface">
        <PanelHeader
          title="Evidence queue"
          description={
            searchQuery
              ? `${filteredEvidence.length} matching records`
              : `${snapshot.evidence.length} records from persisted events`
          }
          action={
            <button
              className="text-action"
              type="button"
              onClick={onClearSearch}
              disabled={!searchQuery}
            >
              Clear filter
            </button>
          }
        />
        <EvidenceTable
          items={filteredEvidence}
          hasQuery={Boolean(searchQuery)}
          onSelect={onOpenEvidence}
          onRefresh={onRefresh}
        />
      </section>
    );
  }

  if (page === "cameras") {
    return (
      <CameraManager
        workspace={activeWorkspace}
        cameras={cameras}
        activeCamera={activeCamera}
        config={snapshot.config}
        onCameraChange={onCameraChange}
        onChanged={async () => {
          await onProductChange();
          onRefresh();
        }}
      />
    );
  }

  if (page === "zones") {
    return (
      <section className="detail-page-grid detail-page-grid-wide">
        <section className="surface">
          <PanelHeader
            title="Scene geometry"
            description={snapshot.config?.camera.name ?? "No camera configuration"}
            action={
              <span className="count-label">{enabledZones.length} enabled</span>
            }
          />
          <SceneMap zones={enabledZones} snapshotUrl={snapshotUrl} />
          <ZoneLegend zones={enabledZones} />
        </section>
        <section className="surface">
          <PanelHeader
            title="Zone inventory"
            description="Normalized coordinates saved with the active camera"
          />
          <ZoneInventory
            zones={snapshot.config?.zones ?? []}
            editable={activeWorkspace?.role !== "viewer"}
            onToggle={async (zone) => {
              if (!activeWorkspace || !activeCamera) return;
              await productApi(
                `/api/workspaces/${activeWorkspace.id}/cameras/${activeCamera.id}/zones/${zone.id}`,
                {
                  method: "PATCH",
                  body: JSON.stringify({ enabled: !zone.enabled })
                }
              );
              onRefresh();
            }}
            onDelete={async (zone) => {
              if (!activeWorkspace || !activeCamera) return;
              await productApi(
                `/api/workspaces/${activeWorkspace.id}/cameras/${activeCamera.id}/zones/${zone.id}`,
                { method: "DELETE" }
              );
              await onProductChange();
              onRefresh();
            }}
          />
          {activeWorkspace && activeCamera && activeWorkspace.role !== "viewer" ? (
            <ZoneCreateForm
              workspaceId={activeWorkspace.id}
              cameraId={activeCamera.id}
              snapshotUrl={snapshotUrl}
              onCreated={async () => {
                await onProductChange();
                onRefresh();
              }}
            />
          ) : null}
        </section>
      </section>
    );
  }

  if (page === "rules") {
    return (
      <section className="detail-page-grid detail-page-grid-wide">
        <section className="surface">
          <PanelHeader
            title="Enforcement rules"
            description="Configured actions evaluated against zone events"
            action={
              <span className="count-label">
                {activeRules.length}/{snapshot.rules.length} active
              </span>
            }
          />
          <RuleList
            rules={snapshot.rules}
            editable={activeWorkspace?.role !== "viewer"}
            onToggle={async (rule) => {
              if (!activeWorkspace || !activeCamera) return;
              await productApi(
                `/api/workspaces/${activeWorkspace.id}/cameras/${activeCamera.id}/rules/${rule.id}`,
                {
                  method: "PATCH",
                  body: JSON.stringify({ enabled: !rule.enabled })
                }
              );
              onRefresh();
            }}
            onDelete={async (rule) => {
              if (!activeWorkspace || !activeCamera) return;
              await productApi(
                `/api/workspaces/${activeWorkspace.id}/cameras/${activeCamera.id}/rules/${rule.id}`,
                { method: "DELETE" }
              );
              await onProductChange();
              onRefresh();
            }}
          />
          {activeWorkspace && activeCamera && activeWorkspace.role !== "viewer" ? (
            <RuleCreateForm
              workspaceId={activeWorkspace.id}
              cameraId={activeCamera.id}
              onCreated={async () => {
                await onProductChange();
                onRefresh();
              }}
            />
          ) : null}
        </section>
        <section className="surface">
          <PanelHeader
            title="Detection thresholds"
            description="Values applied before rule evaluation"
          />
          <PipelineProfile config={snapshot.config} />
        </section>
      </section>
    );
  }

  if (page === "workspace") {
    return (
      <WorkspaceManager
        workspaces={workspaces}
        activeWorkspace={activeWorkspace}
        onWorkspaceChange={onWorkspaceChange}
        onChanged={onProductChange}
      />
    );
  }

  if (page === "team") {
    return (
      <TeamManager
        currentUser={user}
        workspace={activeWorkspace}
        onChanged={onProductChange}
      />
    );
  }

  return (
    <>
      <section className="metric-strip" aria-label="Operational summary">
        <Metric
          label="Configured cameras"
          value={snapshot.config ? "1" : "0"}
          detail={snapshot.config?.camera.source_type ?? "No source loaded"}
          icon={<Camera size={18} aria-hidden="true" />}
        />
        <Metric
          label="Evidence records"
          value={String(snapshot.evidence.length)}
          detail={`${pendingEvidence.length} awaiting review`}
          icon={<ShieldCheck size={18} aria-hidden="true" />}
        />
        <Metric
          label="Active rules"
          value={String(activeRules.length)}
          detail={`${snapshot.rules.length} configured`}
          icon={<SlidersHorizontal size={18} aria-hidden="true" />}
        />
        <Metric
          label="Enabled zones"
          value={String(enabledZones.length)}
          detail={`${zoneTypes(enabledZones)} types in scene`}
          icon={<Map size={18} aria-hidden="true" />}
        />
      </section>

      <section className="dashboard-grid">
        <section className="surface evidence-surface">
          <PanelHeader
            title="Evidence queue"
            description={`${snapshot.evidence.length} records from persisted events`}
            action={
              <PageLink page="evidence" onNavigate={onNavigate}>
                View evidence
              </PageLink>
            }
          />
          <EvidenceTable
            items={snapshot.evidence.slice(0, 5)}
            hasQuery={false}
            onSelect={onOpenEvidence}
            onRefresh={onRefresh}
          />
        </section>

        <aside className="side-stack">
          <section className="surface scene-surface">
            <PanelHeader
              title="Configured scene"
              description={snapshot.config?.camera.name ?? "No camera configuration"}
              action={
                <PageLink page="zones" onNavigate={onNavigate}>
                  View zones
                </PageLink>
              }
            />
            <SceneMap zones={enabledZones} snapshotUrl={snapshotUrl} />
            <ZoneLegend zones={enabledZones} />
          </section>
        </aside>
      </section>

      <section className="lower-grid">
        <section className="surface">
          <PanelHeader
            title="Rule coverage"
            description="Enabled rules evaluated against zone events"
            action={
              <PageLink page="rules" onNavigate={onNavigate}>
                View rules
              </PageLink>
            }
          />
          <RuleList rules={snapshot.rules} />
        </section>

        <section className="surface">
          <PanelHeader
            title="Camera source"
            description={snapshot.config?.camera.id ?? "Not connected"}
            action={
              <PageLink page="cameras" onNavigate={onNavigate}>
                View camera
              </PageLink>
            }
          />
          <SourceDetails config={snapshot.config} />
        </section>
      </section>
    </>
  );
}

function PageLink({
  page,
  onNavigate,
  children
}: {
  page: PageId;
  onNavigate: (
    event: ReactMouseEvent<HTMLAnchorElement>,
    page: PageId
  ) => void;
  children: ReactNode;
}) {
  return (
    <a
      className="panel-link"
      href={`/${page}`}
      onClick={(event) => onNavigate(event, page)}
    >
      {children}
      <ChevronRight size={13} aria-hidden="true" />
    </a>
  );
}

function CameraManager({
  workspace,
  cameras,
  activeCamera,
  config,
  onCameraChange,
  onChanged
}: {
  workspace: WorkspaceSummary | null;
  cameras: CameraSummary[];
  activeCamera: CameraSummary | null;
  config: RoadLensConfig | null;
  onCameraChange: (cameraId: number) => void;
  onChanged: () => Promise<void>;
}) {
  const [creating, setCreating] = useState(false);
  const canEdit = workspace?.role !== "viewer";

  if (!workspace) {
    return <InlineNotice text="Create a workspace before adding cameras." />;
  }

  return (
    <section className="management-grid">
      <Card className="management-list">
        <PanelHeader
          title="Camera inventory"
          description={`${cameras.length} configured in ${workspace.name}`}
          action={
            canEdit ? (
              <Button
                size="sm"
                variant="secondary"
                type="button"
                onClick={() => setCreating(true)}
              >
                <Plus size={15} aria-hidden="true" />
                Add camera
              </Button>
            ) : null
          }
        />
        {cameras.length === 0 ? (
          <InlineNotice text="No cameras yet. Add the first video, RTSP, or webcam source." />
        ) : (
          <div className="camera-list">
            {cameras.map((camera) => (
              <button
                className={`camera-list-row ${
                  activeCamera?.id === camera.id && !creating ? "active" : ""
                }`}
                type="button"
                key={camera.id}
                onClick={() => {
                  setCreating(false);
                  onCameraChange(camera.id);
                }}
              >
                <span className="detail-icon">
                  <Camera size={16} aria-hidden="true" />
                </span>
                <span>
                  <strong>{camera.name}</strong>
                  <small>{camera.source_path}</small>
                </span>
                <span className={`camera-state ${camera.enabled ? "ready" : ""}`}>
                  {camera.enabled ? "Enabled" : "Paused"}
                </span>
              </button>
            ))}
          </div>
        )}
      </Card>

      <Card className="management-editor">
        {creating || !activeCamera ? (
          <>
            <PanelHeader
              title="Add camera"
              description="Create a persisted camera configuration"
            />
            <CameraForm
              workspaceId={workspace.id}
              onSaved={async () => {
                setCreating(false);
                await onChanged();
              }}
            />
          </>
        ) : (
          <>
            <PanelHeader
              title="Camera settings"
              description={activeCamera.camera_key}
              action={
                <span className="status-chip">
                  <CircleDot size={13} aria-hidden="true" />
                  Persisted
                </span>
              }
            />
            <CameraRuntimePanel
              workspaceId={workspace.id}
              camera={activeCamera}
              canEdit={canEdit}
              onCompleted={onChanged}
            />
            <CameraForm
              key={activeCamera.id}
              workspaceId={workspace.id}
              camera={activeCamera}
              config={config}
              onSaved={onChanged}
              onDeleted={async () => {
                setCreating(false);
                await onChanged();
              }}
            />
            {config ? (
              <div className="management-summary">
                <SourceDetails config={config} />
              </div>
            ) : null}
          </>
        )}
      </Card>
    </section>
  );
}

function CameraRuntimePanel({
  workspaceId,
  camera,
  canEdit,
  onCompleted
}: {
  workspaceId: number;
  camera: CameraSummary;
  canEdit: boolean;
  onCompleted: () => Promise<void>;
}) {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [snapshotVersion, setSnapshotVersion] = useState(Date.now());
  const [snapshotAvailable, setSnapshotAvailable] = useState(true);
  const completedJobRef = useRef<number | null>(null);
  const onCompletedRef = useRef(onCompleted);

  useEffect(() => {
    onCompletedRef.current = onCompleted;
  }, [onCompleted]);

  const loadJobs = useCallback(async () => {
    const payload = await productApi<{ items: ProcessingJob[] }>(
      `/api/workspaces/${workspaceId}/jobs?camera_id=${camera.id}&limit=5`
    );
    setJobs(payload.items);
    const completedJob = payload.items.find((item) => item.status === "completed");
    if (completedJob && completedJob.id !== completedJobRef.current) {
      completedJobRef.current = completedJob.id;
      await onCompletedRef.current();
    }
  }, [camera.id, workspaceId]);

  useEffect(() => {
    setError(null);
    setSnapshotAvailable(true);
    setSnapshotVersion(Date.now());
    void loadJobs().catch((loadError) =>
      setError(
        loadError instanceof Error ? loadError.message : "Could not load processing jobs"
      )
    );
    const timer = window.setInterval(() => {
      void loadJobs().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [loadJobs]);

  const activeJob = jobs.find((job) =>
    ["queued", "running", "cancel_requested"].includes(job.status)
  );
  const latestJob = activeJob ?? jobs[0] ?? null;
  const snapshotUrl = cameraSnapshotUrl(
    workspaceId,
    camera.id,
    `${camera.updated_at}-${snapshotVersion}`
  );

  const startProcessing = async () => {
    setBusy(true);
    setError(null);
    try {
      const job = await productApi<ProcessingJob>(
        `/api/workspaces/${workspaceId}/jobs`,
        {
          method: "POST",
          body: JSON.stringify({ camera_id: camera.id, job_type: "process_camera" })
        }
      );
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
    } catch (startError) {
      setError(
        startError instanceof Error ? startError.message : "Could not start processing"
      );
    } finally {
      setBusy(false);
    }
  };

  const cancelProcessing = async () => {
    if (!activeJob) return;
    setBusy(true);
    setError(null);
    try {
      const job = await productApi<ProcessingJob>(
        `/api/workspaces/${workspaceId}/jobs/${activeJob.id}/cancel`,
        { method: "POST" }
      );
      setJobs((current) =>
        current.map((item) => (item.id === job.id ? job : item))
      );
    } catch (cancelError) {
      setError(
        cancelError instanceof Error ? cancelError.message : "Could not cancel processing"
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="camera-runtime">
      <div className="camera-preview">
        {snapshotAvailable ? (
          <img
            src={snapshotUrl}
            alt={`Current frame from ${camera.name}`}
            onError={() => setSnapshotAvailable(false)}
          />
        ) : (
          <div className="camera-preview-empty">
            <FileVideo size={22} aria-hidden="true" />
            <span>Frame unavailable</span>
          </div>
        )}
        <Button
          className="camera-preview-refresh"
          variant="secondary"
          size="icon"
          type="button"
          aria-label="Refresh camera frame"
          onClick={() => {
            setSnapshotAvailable(true);
            setSnapshotVersion(Date.now());
          }}
        >
          <RefreshCw size={15} aria-hidden="true" />
        </Button>
      </div>
      <div className="camera-runtime-copy">
        <div>
          <span className="eyebrow">Processing</span>
          <strong>{latestJob ? humanize(latestJob.status) : "Ready"}</strong>
          <p>
            {latestJob?.error ??
              latestJob?.progress?.message ??
              (latestJob?.result?.detection_count != null
                ? `${latestJob.result.detection_count} detections saved.`
                : "Run the configured pipeline against this source.")}
          </p>
        </div>
        <div className="camera-runtime-actions">
          {activeJob ? (
            <Button
              variant="outline"
              type="button"
              disabled={busy || activeJob.status === "cancel_requested" || !canEdit}
              onClick={cancelProcessing}
            >
              <Square size={13} aria-hidden="true" />
              {activeJob.status === "cancel_requested" ? "Canceling" : "Cancel"}
            </Button>
          ) : (
            <Button
              type="button"
              disabled={busy || !canEdit || !camera.enabled}
              onClick={startProcessing}
            >
              <Play size={14} aria-hidden="true" />
              {busy ? "Starting" : "Run processing"}
            </Button>
          )}
        </div>
      </div>
      {error ? <p className="form-error camera-runtime-error">{error}</p> : null}
    </section>
  );
}

function CameraForm({
  workspaceId,
  camera,
  config,
  onSaved,
  onDeleted
}: {
  workspaceId: number;
  camera?: CameraSummary;
  config?: RoadLensConfig | null;
  onSaved: () => Promise<void>;
  onDeleted?: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<CameraSummary["source_type"]>(
    camera?.source_type ?? "video_file"
  );

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    let sourcePath = String(form.get("source_path") ?? "").trim();
    const sourceUsername = String(form.get("source_username") ?? "").trim();
    const sourcePassword = String(form.get("source_password") ?? "");

    try {
      if (sourceType === "video_file") {
        const video = form.get("video_file");
        if (video instanceof File && video.size > 0) {
          const upload = new FormData();
          upload.set("video", video);
          const response = await fetch(
            `/api/workspaces/${workspaceId}/camera-sources/video`,
            { method: "POST", body: upload }
          );
          if (!response.ok) {
            const payload = (await response.json().catch(() => null)) as {
              detail?: string;
            } | null;
            throw new Error(payload?.detail ?? "Video upload failed.");
          }
          const uploaded = (await response.json()) as { source_path: string };
          sourcePath = uploaded.source_path;
        }
      }

      if (!sourcePath) {
        throw new Error(
          sourceType === "video_file"
            ? "Choose a video file."
            : "Enter the source address."
        );
      }

      const payload = {
        name: form.get("name"),
        camera_key: form.get("camera_key") || undefined,
        source_type: sourceType,
        source_path: sourcePath,
        reference_width: Number(form.get("reference_width")),
        reference_height: Number(form.get("reference_height")),
        timezone: form.get("timezone"),
        enabled: form.get("enabled") === "on",
        ...(sourceType === "rtsp" && (sourceUsername || sourcePassword)
          ? {
              source_username: sourceUsername,
              source_password: sourcePassword
            }
          : {}),
        ...(camera && sourceType === "rtsp"
          ? {
              clear_source_credentials:
                form.get("clear_source_credentials") === "on"
            }
          : {}),
        ...(camera && config
          ? {
              vehicle_detector: form.get("vehicle_detector"),
              plate_detector: form.get("plate_detector"),
              motion_threshold: Number(form.get("motion_threshold")),
              cooldown_frames: Number(form.get("cooldown_frames")),
              vehicle_confidence: Number(form.get("vehicle_confidence")),
              plate_confidence: Number(form.get("plate_confidence")),
              save_to_db: form.get("save_to_db") === "on",
              save_evidence_images: form.get("save_evidence_images") === "on"
            }
          : {})
      };

      await productApi(
        camera
          ? `/api/workspaces/${workspaceId}/cameras/${camera.id}`
          : `/api/workspaces/${workspaceId}/cameras`,
        {
          method: camera ? "PATCH" : "POST",
          body: JSON.stringify(payload)
        }
      );
      await onSaved();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Could not save camera"
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="management-form" onSubmit={submit}>
      <div className="form-grid">
        <Label>
          Camera name
          <Input name="name" defaultValue={camera?.name} required minLength={2} />
        </Label>
        <Label>
          Camera key
          <Input
            name="camera_key"
            defaultValue={camera?.camera_key}
            placeholder="generated-from-name"
          />
        </Label>
        <Label>
          Source type
          <Select
            name="source_type"
            value={sourceType}
            onValueChange={(value) =>
              setSourceType(value as CameraSummary["source_type"])
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="video_file">Video upload</SelectItem>
              <SelectItem value="rtsp">RTSP live stream</SelectItem>
              <SelectItem value="webcam">Webcam</SelectItem>
            </SelectContent>
          </Select>
        </Label>
        {sourceType === "video_file" ? (
          <Label>
            Video file
            <Input
              name="video_file"
              type="file"
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo"
              required={!camera || camera.source_type !== "video_file"}
            />
            {camera?.source_type === "video_file" ? (
              <small className="field-help">Current: {camera.source_path}</small>
            ) : null}
            <input
              name="source_path"
              type="hidden"
              value={camera?.source_type === "video_file" ? camera.source_path : ""}
            />
          </Label>
        ) : (
          <>
            <Label>
              {sourceType === "rtsp" ? "RTSP URL" : "Device index"}
              <Input
                name="source_path"
                defaultValue={
                  camera?.source_type === sourceType
                    ? camera.source_path
                    : sourceType === "webcam"
                      ? "0"
                      : ""
                }
                placeholder={sourceType === "rtsp" ? "rtsp://camera/stream" : "0"}
                required
              />
            </Label>
            {sourceType === "rtsp" ? (
              <>
                <Label>
                  Source username
                  <Input
                    name="source_username"
                    autoComplete="off"
                    placeholder={
                      camera?.has_source_credentials ? "Saved securely" : "Optional"
                    }
                  />
                </Label>
                <Label>
                  Source password
                  <Input
                    name="source_password"
                    type="password"
                    autoComplete="new-password"
                    placeholder={
                      camera?.has_source_credentials ? "Saved securely" : "Optional"
                    }
                  />
                </Label>
                {camera?.has_source_credentials ? (
                  <Label className="switch-row">
                    <Switch name="clear_source_credentials" />
                    Remove saved credentials
                  </Label>
                ) : null}
              </>
            ) : null}
          </>
        )}
        <Label>
          Reference width
          <Input
            name="reference_width"
            type="number"
            min={1}
            defaultValue={camera?.reference_resolution[0] ?? 1920}
            required
          />
        </Label>
        <Label>
          Reference height
          <Input
            name="reference_height"
            type="number"
            min={1}
            defaultValue={camera?.reference_resolution[1] ?? 1080}
            required
          />
        </Label>
        <Label className="form-span">
          Timezone
          <Input
            name="timezone"
            defaultValue={camera?.timezone ?? "Asia/Kathmandu"}
            required
          />
        </Label>
      </div>
      <Label className="switch-row">
        <Switch name="enabled" defaultChecked={camera?.enabled ?? true} />
        Enabled
      </Label>
      {camera && config ? (
        <fieldset className="config-fieldset">
          <legend>Pipeline configuration</legend>
          <div className="form-grid">
            <Label>
              Vehicle detector
              <Input
                name="vehicle_detector"
                defaultValue={config.models.vehicle_detector}
                required
              />
            </Label>
            <Label>
              Plate detector
              <Input
                name="plate_detector"
                defaultValue={config.models.plate_detector}
                required
              />
            </Label>
            <Label>
              Motion threshold
              <Input
                name="motion_threshold"
                type="number"
                min={1}
                defaultValue={config.frame_selection.motion_threshold}
                required
              />
            </Label>
            <Label>
              Cooldown frames
              <Input
                name="cooldown_frames"
                type="number"
                min={0}
                defaultValue={config.frame_selection.cooldown_frames}
                required
              />
            </Label>
            <Label>
              Vehicle confidence
              <Input
                name="vehicle_confidence"
                type="number"
                min={0}
                max={1}
                step={0.01}
                defaultValue={config.detection.vehicle_confidence}
                required
              />
            </Label>
            <Label>
              Plate confidence
              <Input
                name="plate_confidence"
                type="number"
                min={0}
                max={1}
                step={0.01}
                defaultValue={config.detection.plate_confidence}
                required
              />
            </Label>
          </div>
          <Label className="switch-row">
            <Switch
              name="save_to_db"
              defaultChecked={config.storage.save_to_db}
            />
            Save evidence records
          </Label>
          <Label className="switch-row">
            <Switch
              name="save_evidence_images"
              defaultChecked={config.storage.save_evidence_images}
            />
            Save evidence images
          </Label>
        </fieldset>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      <div className="form-actions">
        {camera && onDeleted ? (
          <Button
            variant="destructive"
            type="button"
            disabled={busy}
            onClick={async () => {
              if (!window.confirm(`Delete ${camera.name}?`)) return;
              setBusy(true);
              try {
                await productApi(
                  `/api/workspaces/${workspaceId}/cameras/${camera.id}`,
                  { method: "DELETE" }
                );
                await onDeleted();
              } catch (deleteError) {
                setError(
                  deleteError instanceof Error
                    ? deleteError.message
                    : "Could not delete camera"
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            <Trash2 size={15} aria-hidden="true" />
            Delete
          </Button>
        ) : null}
        <Button
          type="submit"
          disabled={busy}
          data-state={busy ? "loading" : undefined}
        >
          {busy ? "Saving" : camera ? "Save changes" : "Add camera"}
        </Button>
      </div>
    </form>
  );
}

function WorkspaceManager({
  workspaces,
  activeWorkspace,
  onWorkspaceChange,
  onChanged
}: {
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary | null;
  onWorkspaceChange: (workspaceId: number) => void;
  onChanged: () => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const saveWorkspace = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!activeWorkspace) return;
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      await productApi(`/api/workspaces/${activeWorkspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: form.get("name"),
          timezone: form.get("timezone")
        })
      });
      await onChanged();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save");
    } finally {
      setBusy(false);
    }
  };

  const createWorkspace = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const created = await productApi<WorkspaceSummary>("/api/workspaces", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          timezone: form.get("timezone")
        })
      });
      await onChanged();
      onWorkspaceChange(created.id);
      event.currentTarget.reset();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Could not create");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="management-grid">
      <section className="surface management-list">
        <PanelHeader
          title="Your workspaces"
          description={`${workspaces.length} accessible workspace${
            workspaces.length === 1 ? "" : "s"
          }`}
        />
        <div className="workspace-list">
          {workspaces.map((workspace) => (
            <button
              className={`workspace-list-row ${
                workspace.id === activeWorkspace?.id ? "active" : ""
              }`}
              type="button"
              key={workspace.id}
              onClick={() => onWorkspaceChange(workspace.id)}
            >
              <span className="detail-icon">
                <Warehouse size={16} aria-hidden="true" />
              </span>
              <span>
                <strong>{workspace.name}</strong>
                <small>
                  {workspace.camera_count} cameras · {workspace.member_count} members
                </small>
              </span>
              <small>{humanize(workspace.role)}</small>
            </button>
          ))}
        </div>
      </section>
      <div className="side-stack">
        {activeWorkspace ? (
          <section className="surface">
            <PanelHeader
              title="Workspace settings"
              description={activeWorkspace.slug}
            />
            <form className="management-form" onSubmit={saveWorkspace}>
              <label>
                Workspace name
                <input
                  name="name"
                  defaultValue={activeWorkspace.name}
                  disabled={activeWorkspace.role === "viewer"}
                  required
                />
              </label>
              <label>
                Timezone
                <input
                  name="timezone"
                  defaultValue={activeWorkspace.timezone}
                  disabled={activeWorkspace.role === "viewer"}
                  required
                />
              </label>
              {error ? <p className="form-error">{error}</p> : null}
              <button
                className="button button-primary"
                type="submit"
                disabled={busy || activeWorkspace.role === "viewer"}
              >
                Save workspace
              </button>
            </form>
          </section>
        ) : null}
        <section className="surface">
          <PanelHeader
            title="Create workspace"
            description="Start a separate camera and team environment"
          />
          <form className="management-form" onSubmit={createWorkspace}>
            <label>
              Workspace name
              <input name="name" required minLength={2} />
            </label>
            <label>
              Timezone
              <input name="timezone" defaultValue="Asia/Kathmandu" required />
            </label>
            <button className="button button-secondary" type="submit" disabled={busy}>
              <Plus size={15} aria-hidden="true" />
              Create workspace
            </button>
          </form>
        </section>
      </div>
    </section>
  );
}

type MemberSummary = UserSummary & {
  role: "owner" | "admin" | "operator" | "viewer";
};

type InvitationSummary = {
  id: number;
  email: string;
  name: string;
  role: "owner" | "admin" | "operator" | "viewer";
  expires_at: string;
};

function TeamManager({
  currentUser,
  workspace,
  onChanged
}: {
  currentUser: UserSummary;
  workspace: WorkspaceSummary | null;
  onChanged: () => Promise<void>;
}) {
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [invitations, setInvitations] = useState<InvitationSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canManage = workspace?.role === "owner" || workspace?.role === "admin";

  const loadMembers = useCallback(async () => {
    if (!workspace) return;
    const payload = await productApi<{ items: MemberSummary[] }>(
      `/api/workspaces/${workspace.id}/members`
    );
    setMembers(payload.items);
  }, [workspace]);

  const loadInvitations = useCallback(async () => {
    if (!workspace || !canManage) {
      setInvitations([]);
      return;
    }
    const payload = await productApi<{ items: InvitationSummary[] }>(
      `/api/workspaces/${workspace.id}/invitations`
    );
    setInvitations(payload.items);
  }, [canManage, workspace]);

  useEffect(() => {
    void Promise.all([loadMembers(), loadInvitations()]).catch((loadError) =>
      setError(loadError instanceof Error ? loadError.message : "Could not load team")
    );
  }, [loadInvitations, loadMembers]);

  if (!workspace) {
    return <InlineNotice text="Create a workspace before adding team members." />;
  }

  const inviteMember = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      await productApi(`/api/workspaces/${workspace.id}/invitations`, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          role: form.get("role")
        })
      });
      event.currentTarget.reset();
      setSuccess(`Invitation sent to ${String(form.get("email"))}.`);
      await loadInvitations();
    } catch (addError) {
      setError(
        addError instanceof Error ? addError.message : "Could not send invitation"
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="team-settings">
      <section className="management-grid">
        <section className="surface management-list">
          <PanelHeader
            title="Workspace members"
            description={`${members.length} user${members.length === 1 ? "" : "s"}`}
          />
          <div className="member-list">
            {members.map((member) => (
              <article className="member-row" key={member.id}>
                <span className="member-avatar" aria-hidden="true">
                  {initials(member.name)}
                </span>
                <span>
                  <strong>
                    {member.name}
                    {member.id === currentUser.id ? " · You" : ""}
                  </strong>
                  <small>{member.email}</small>
                </span>
                <select
                  aria-label={`Role for ${member.name}`}
                  value={member.role}
                  disabled={!canManage}
                  onChange={async (event) => {
                    await productApi(
                      `/api/workspaces/${workspace.id}/members/${member.id}`,
                      {
                        method: "PATCH",
                        body: JSON.stringify({ role: event.target.value })
                      }
                    );
                    await loadMembers();
                    await onChanged();
                  }}
                >
                  <option value="owner">Owner</option>
                  <option value="admin">Admin</option>
                  <option value="operator">Operator</option>
                  <option value="viewer">Viewer</option>
                </select>
                {canManage && member.id !== currentUser.id ? (
                  <button
                    className="icon-button subtle-danger"
                    type="button"
                    aria-label={`Remove ${member.name}`}
                    onClick={async () => {
                      if (!window.confirm(`Remove ${member.name} from this workspace?`))
                        return;
                      await productApi(
                        `/api/workspaces/${workspace.id}/members/${member.id}`,
                        { method: "DELETE" }
                      );
                      await loadMembers();
                      await onChanged();
                    }}
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        </section>
        <section className="surface">
          <PanelHeader
            title="Invite teammate"
            description="They’ll choose their own password"
          />
          <form className="management-form" onSubmit={inviteMember}>
            <label>
              Full name
              <input name="name" required minLength={2} disabled={!canManage} />
            </label>
            <label>
              Email
              <input name="email" type="email" required disabled={!canManage} />
            </label>
            <label>
              Role
              <select name="role" defaultValue="operator" disabled={!canManage}>
                <option value="admin">Admin</option>
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </select>
            </label>
            {success ? <p className="form-success compact">{success}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
            <button
              className="button button-primary"
              type="submit"
              disabled={busy || !canManage}
            >
              <Mail size={15} aria-hidden="true" />
              Send invitation
            </button>
          </form>
          {invitations.length > 0 ? (
            <div className="pending-invites">
              <span className="eyebrow">Pending</span>
              {invitations.map((item) => (
                <div className="pending-invite" key={item.id}>
                  <span>
                    <strong>{item.name}</strong>
                    <small>{item.email} · {item.role}</small>
                  </span>
                  <button
                    className="icon-button subtle-danger"
                    type="button"
                    aria-label={`Revoke invitation for ${item.email}`}
                    onClick={async () => {
                      await productApi(
                        `/api/workspaces/${workspace.id}/invitations/${item.id}`,
                        { method: "DELETE" }
                      );
                      await loadInvitations();
                    }}
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      </section>
      <AccountSecurity currentUser={currentUser} onChanged={onChanged} />
    </div>
  );
}

function AccountSecurity({
  currentUser,
  onChanged
}: {
  currentUser: UserSummary;
  onChanged: () => Promise<void>;
}) {
  const [status, setStatus] = useState<{
    mfa_enabled: boolean;
    recovery_codes_remaining: number;
    sso_linked: boolean;
    sso_provider_name: string | null;
  } | null>(null);
  const [enrollment, setEnrollment] = useState<{
    secret: string;
    provisioning_uri: string;
  } | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadSecurity = useCallback(async () => {
    setStatus(await productApi("/api/auth/security"));
  }, []);

  useEffect(() => {
    void loadSecurity().catch((loadError) =>
      setError(
        loadError instanceof Error ? loadError.message : "Could not load security"
      )
    );
  }, [loadSecurity]);

  return (
    <section className="surface account-security">
      <PanelHeader
        title="Account security"
        description="Protect your account with an authenticator app"
      />
      <div className="security-summary">
        <span className="security-icon" aria-hidden="true">
          <ShieldCheck size={19} />
        </span>
        <span>
          <strong>
            Two-factor authentication {status?.mfa_enabled ? "is on" : "is off"}
          </strong>
          <small>
            {status?.mfa_enabled
              ? `${status.recovery_codes_remaining} recovery codes remaining`
              : `Signed in as ${currentUser.email}`}
          </small>
        </span>
        {!status?.mfa_enabled && !enrollment ? (
          <button
            className="button button-secondary"
            type="button"
            onClick={async () => {
              setError(null);
              setEnrollment(await productApi("/api/auth/mfa/enroll", { method: "POST" }));
            }}
          >
            Set up MFA
          </button>
        ) : null}
      </div>
      {status?.sso_linked ? (
        <div className="linked-identity">
          <span className="security-icon" aria-hidden="true">
            <Building2 size={19} />
          </span>
          <span>
            <strong>Single sign-on is linked</strong>
            <small>
              {status.sso_provider_name ?? "Your identity provider"} can sign in
              to this account.
            </small>
          </span>
        </div>
      ) : null}
      {enrollment ? (
        <form
          className="security-form"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            try {
              const result = await productApi<{
                recovery_codes: string[];
              }>("/api/auth/mfa/confirm", {
                method: "POST",
                body: JSON.stringify({ code: form.get("code") })
              });
              setRecoveryCodes(result.recovery_codes);
              setEnrollment(null);
              await loadSecurity();
              await onChanged();
            } catch (confirmError) {
              setError(
                confirmError instanceof Error
                  ? confirmError.message
                  : "Could not enable MFA"
              );
            }
          }}
        >
          <div className="setup-key">
            <span>Add this setup key to your authenticator app</span>
            <code>{enrollment.secret}</code>
          </div>
          <label>
            6-digit code
            <input
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              minLength={6}
              maxLength={6}
              required
            />
          </label>
          <button className="button button-primary" type="submit">
            Verify and enable
          </button>
        </form>
      ) : null}
      {recoveryCodes.length > 0 ? (
        <div className="recovery-codes" role="status">
          <strong>Save these recovery codes now</strong>
          <span>Each code can be used once. Store them in a password manager.</span>
          <div>
            {recoveryCodes.map((code) => <code key={code}>{code}</code>)}
          </div>
        </div>
      ) : null}
      {status?.mfa_enabled ? (
        <details className="security-actions">
          <summary>Manage MFA</summary>
          <form
            className="security-form security-form-simple"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              try {
                const result = await productApi<{ recovery_codes: string[] }>(
                  "/api/auth/mfa/recovery-codes",
                  {
                    method: "POST",
                    body: JSON.stringify({ code: form.get("code") })
                  }
                );
                setRecoveryCodes(result.recovery_codes);
                event.currentTarget.reset();
                await loadSecurity();
              } catch (regenerateError) {
                setError(
                  regenerateError instanceof Error
                    ? regenerateError.message
                    : "Could not create recovery codes"
                );
              }
            }}
          >
            <label>
              Authentication code
              <input name="code" autoComplete="one-time-code" required />
            </label>
            <button className="button button-secondary" type="submit">
              Replace recovery codes
            </button>
          </form>
          <form
            className="security-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              try {
                await productApi("/api/auth/mfa/disable", {
                  method: "POST",
                  body: JSON.stringify({
                    password: form.get("password"),
                    code: form.get("code")
                  })
                });
                setRecoveryCodes([]);
                await loadSecurity();
                await onChanged();
              } catch (disableError) {
                setError(
                  disableError instanceof Error
                    ? disableError.message
                    : "Could not disable MFA"
                );
              }
            }}
          >
            <label>
              Current password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                minLength={8}
                required
              />
            </label>
            <label>
              Authentication or recovery code
              <input name="code" autoComplete="one-time-code" required />
            </label>
            <button className="button button-danger" type="submit">
              Disable MFA
            </button>
          </form>
        </details>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
    </section>
  );
}

function ZoneCreateForm({
  workspaceId,
  cameraId,
  snapshotUrl,
  onCreated
}: {
  workspaceId: number;
  cameraId: number;
  snapshotUrl?: string;
  onCreated: () => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [points, setPoints] = useState<Array<[number, number]>>([]);
  const [zoneType, setZoneType] = useState("restricted_zone");

  const addPoint = (event: ReactMouseEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width;
    const y = (event.clientY - bounds.top) / bounds.height;
    setPoints((current) => [
      ...current,
      [Number(x.toFixed(4)), Number(y.toFixed(4))]
    ]);
  };

  return (
    <form
      className="zone-create-form"
      onSubmit={async (event) => {
        event.preventDefault();
        if (points.length < 3) {
          setError("Add at least three points.");
          return;
        }
        const form = new FormData(event.currentTarget);
        const id = slugId(String(form.get("name")));
        try {
          await productApi(
            `/api/workspaces/${workspaceId}/cameras/${cameraId}/zones`,
            {
              method: "POST",
              body: JSON.stringify({
                id,
                name: form.get("name"),
                type: zoneType,
                shape: "polygon",
                enabled: true,
                description: form.get("description") || null,
                points_normalized: points
              })
            }
          );
          event.currentTarget.reset();
          setPoints([]);
          await onCreated();
        } catch (createError) {
          setError(
            createError instanceof Error ? createError.message : "Could not add zone"
          );
        }
      }}
    >
      <div className="zone-create-head">
        <div>
          <strong>Add zone</strong>
          <span>Click the canvas to place polygon points.</span>
        </div>
        <span className="count-label">{points.length} points</span>
      </div>
      <div className="zone-create-grid">
        <div className="zone-create-fields">
          <Label>
            Name
            <Input name="name" required />
          </Label>
          <Label>
            Type
            <Select value={zoneType} onValueChange={setZoneType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="detection_roi">Detection ROI</SelectItem>
                <SelectItem value="stop_line">Stop line</SelectItem>
                <SelectItem value="zebra_crossing">Zebra crossing</SelectItem>
                <SelectItem value="restricted_zone">Restricted zone</SelectItem>
                <SelectItem value="no_entry">No entry</SelectItem>
              </SelectContent>
            </Select>
          </Label>
          <Label>
            Description
            <Input name="description" />
          </Label>
        </div>
        <div>
          <svg
            className="zone-draw-canvas"
            viewBox="0 0 100 56"
            role="application"
            aria-label="Click to draw a normalized zone polygon"
            onClick={addPoint}
          >
            {snapshotUrl ? (
              <image
                className="scene-snapshot"
                href={snapshotUrl}
                width="100"
                height="56"
                preserveAspectRatio="none"
              />
            ) : null}
            {points.length > 1 ? (
              <polyline
                className="zone-draw-shape"
                points={points.map(([x, y]) => `${x * 100},${y * 56}`).join(" ")}
              />
            ) : null}
            {points.map(([x, y], index) => (
              <circle
                className="zone-draw-point"
                key={`${x}-${y}-${index}`}
                cx={x * 100}
                cy={y * 56}
                r="1.35"
              />
            ))}
          </svg>
          <div className="zone-draw-actions">
            <Button
              size="sm"
              variant="ghost"
              type="button"
              disabled={points.length === 0}
              onClick={() => setPoints((current) => current.slice(0, -1))}
            >
              Undo
            </Button>
            <Button
              size="sm"
              variant="ghost"
              type="button"
              disabled={points.length === 0}
              onClick={() => setPoints([])}
            >
              Clear
            </Button>
            <Button size="sm" type="submit" disabled={points.length < 3}>
              <Plus size={15} aria-hidden="true" />
              Add zone
            </Button>
          </div>
        </div>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
    </form>
  );
}

function RuleCreateForm({
  workspaceId,
  cameraId,
  onCreated
}: {
  workspaceId: number;
  cameraId: number;
  onCreated: () => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="inline-create-form"
      onSubmit={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        try {
          await productApi(
            `/api/workspaces/${workspaceId}/cameras/${cameraId}/rules`,
            {
              method: "POST",
              body: JSON.stringify({
                id: slugId(String(form.get("name"))),
                name: form.get("name"),
                enabled: true,
                when: {
                  all: [
                    {
                      kind: "zone_event",
                      event: "vehicle_intersects_zone",
                      zone_type: form.get("zone_type")
                    }
                  ]
                },
                actions: [
                  "create_violation_event",
                  "capture_license_plate",
                  "send_to_review"
                ]
              })
            }
          );
          event.currentTarget.reset();
          await onCreated();
        } catch (createError) {
          setError(
            createError instanceof Error ? createError.message : "Could not add rule"
          );
        }
      }}
    >
      <strong>Add rule</strong>
      <input name="name" placeholder="Rule name" aria-label="Rule name" required />
      <select name="zone_type" aria-label="Target zone type">
        <option value="stop_line">Stop line</option>
        <option value="zebra_crossing">Zebra crossing</option>
        <option value="restricted_zone">Restricted zone</option>
        <option value="no_entry">No entry</option>
      </select>
      <button className="button button-secondary" type="submit">
        <Plus size={15} aria-hidden="true" />
        Add rule
      </button>
      {error ? <p className="form-error form-span">{error}</p> : null}
    </form>
  );
}

function InlineNotice({ text }: { text: string }) {
  return (
    <section className="surface inline-empty">
      <CircleDot size={18} aria-hidden="true" />
      <span>{text}</span>
    </section>
  );
}

function Sidebar({
  user,
  workspaces,
  activeWorkspace,
  cameras,
  activeCamera,
  loadState,
  activePage,
  onNavigate,
  onWorkspaceChange,
  onCameraChange,
  onLogout
}: {
  user: UserSummary;
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary | null;
  cameras: CameraSummary[];
  activeCamera: CameraSummary | null;
  loadState: LoadState;
  activePage: PageId;
  onNavigate: (
    event: ReactMouseEvent<HTMLAnchorElement>,
    page: PageId
  ) => void;
  onWorkspaceChange: (workspaceId: number) => void;
  onCameraChange: (cameraId: number) => void;
  onLogout: () => Promise<void>;
}) {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <ScanLine size={19} />
        </span>
        <div>
          <strong>RoadLens</strong>
        </div>
      </div>

      <div className="workspace-switcher">
        <span className="workspace-icon" aria-hidden="true">
          <Warehouse size={16} />
        </span>
        <label>
          <small>Workspace</small>
          <select
            aria-label="Active workspace"
            value={activeWorkspace?.id ?? ""}
            onChange={(event) => onWorkspaceChange(Number(event.target.value))}
          >
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="camera-switcher">
        <span>Camera</span>
        <select
          value={activeCamera?.id ?? ""}
          disabled={cameras.length === 0}
          onChange={(event) => onCameraChange(Number(event.target.value))}
        >
          {cameras.length === 0 ? (
            <option value="">No cameras configured</option>
          ) : null}
          {cameras.map((camera) => (
            <option key={camera.id} value={camera.id}>
              {camera.name}
            </option>
          ))}
        </select>
      </label>

      <nav className="sidebar-nav">
        <span className="nav-group-label">Monitor</span>
        <a
          className={`nav-link ${activePage === "overview" ? "active" : ""}`}
          href="/overview"
          aria-current={activePage === "overview" ? "page" : undefined}
          onClick={(event) => onNavigate(event, "overview")}
        >
          <LayoutDashboard size={17} aria-hidden="true" />
          Overview
        </a>
        <a
          className={`nav-link ${activePage === "evidence" ? "active" : ""}`}
          href="/evidence"
          aria-current={activePage === "evidence" ? "page" : undefined}
          onClick={(event) => onNavigate(event, "evidence")}
        >
          <ShieldCheck size={17} aria-hidden="true" />
          Evidence
        </a>
        <a
          className={`nav-link ${activePage === "cameras" ? "active" : ""}`}
          href="/cameras"
          aria-current={activePage === "cameras" ? "page" : undefined}
          onClick={(event) => onNavigate(event, "cameras")}
        >
          <Camera size={17} aria-hidden="true" />
          Cameras
        </a>

        <span className="nav-group-label nav-group-spaced">Configure</span>
        <a
          className={`nav-link ${activePage === "zones" ? "active" : ""}`}
          href="/zones"
          aria-current={activePage === "zones" ? "page" : undefined}
          onClick={(event) => onNavigate(event, "zones")}
        >
          <Map size={17} aria-hidden="true" />
          Zones
        </a>
        <a
          className={`nav-link ${activePage === "rules" ? "active" : ""}`}
          href="/rules"
          aria-current={activePage === "rules" ? "page" : undefined}
          onClick={(event) => onNavigate(event, "rules")}
        >
          <SlidersHorizontal size={17} aria-hidden="true" />
          Rules
        </a>

        <span className="nav-group-label nav-group-spaced">Manage</span>
        <a
          className={`nav-link ${activePage === "workspace" ? "active" : ""}`}
          href="/workspace"
          aria-current={activePage === "workspace" ? "page" : undefined}
          onClick={(event) => onNavigate(event, "workspace")}
        >
          <Warehouse size={17} aria-hidden="true" />
          Workspace
        </a>
        <a
          className={`nav-link ${activePage === "team" ? "active" : ""}`}
          href="/team"
          aria-current={activePage === "team" ? "page" : undefined}
          onClick={(event) => onNavigate(event, "team")}
        >
          <Users size={17} aria-hidden="true" />
          Team
        </a>
      </nav>

      <div className="sidebar-status">
        <div className="sidebar-status-head">
          <span className={`api-dot api-dot-${loadState}`} aria-hidden="true" />
          <strong>RoadLens API</strong>
        </div>
        <span>{statusCopy(loadState)}</span>
        <div className="sidebar-account">
          <span>
            <strong>{user.name}</strong>
            <small>{user.email}</small>
          </span>
          <button
            type="button"
            aria-label="Sign out"
            title="Sign out"
            onClick={() => void onLogout()}
          >
            <LogOut size={16} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}

function StatusLine({
  state,
  message,
  cameraName,
  lastSyncedAt
}: {
  state: LoadState;
  message: string | null;
  cameraName?: string;
  lastSyncedAt: Date | null;
}) {
  if (state === "error") {
    return (
      <div className="system-line system-line-error" role="status">
        <AlertCircle size={16} aria-hidden="true" />
        <span>
          Backend data could not be loaded. {message ?? "Check the API service."}
        </span>
      </div>
    );
  }

  return (
    <div className="system-line" role="status" aria-live="polite">
      <span className={`api-dot api-dot-${state}`} aria-hidden="true" />
      <span>
        {state === "loading"
          ? "Syncing"
          : cameraName
            ? `${cameraName} is ready`
            : "No camera selected"}
      </span>
      {lastSyncedAt ? (
        <time dateTime={lastSyncedAt.toISOString()}>
          Synced {formatTime(lastSyncedAt)}
        </time>
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  icon
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
}) {
  return (
    <article className="metric">
      <div className="metric-top">
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function PanelHeader({
  title,
  description,
  action
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="panel-header">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}

function EvidenceTable({
  items,
  hasQuery,
  onSelect,
  onRefresh
}: {
  items: EvidenceItem[];
  hasQuery: boolean;
  onSelect: (item: EvidenceItem) => void;
  onRefresh: () => void;
}) {
  if (items.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon" aria-hidden="true">
          <Database size={21} />
        </span>
        <h3>{hasQuery ? "No matching evidence" : "No evidence records yet"}</h3>
        <p>
          {hasQuery
            ? "Try a plate, rule, zone, or review status."
            : "Run the configured pipeline with persistence enabled. New violation events will appear here."}
        </p>
        {!hasQuery ? (
          <button className="button button-secondary" type="button" onClick={onRefresh}>
            <RefreshCw size={15} aria-hidden="true" />
            Check again
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="evidence-table" role="table" aria-label="Violation evidence">
      <div className="evidence-head" role="row">
        <span role="columnheader">Plate</span>
        <span role="columnheader">Rule</span>
        <span role="columnheader">Zone</span>
        <span role="columnheader">Captured</span>
        <span role="columnheader">Review</span>
        <span aria-hidden="true" />
      </div>
      {items.map((item) => (
        <button
          className="evidence-row"
          type="button"
          role="row"
          key={item.id}
          onClick={() => onSelect(item)}
        >
          <strong role="cell">{plateLabel(item)}</strong>
          <span role="cell">{item.rule.name}</span>
          <span role="cell">{item.zone.name}</span>
          <time role="cell" dateTime={item.created_at}>
            {formatEvidenceTime(item)}
          </time>
          <span role="cell">
            <ReviewBadge status={item.review_status} />
          </span>
          <ChevronRight size={15} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

function ReviewBadge({ status }: { status: string }) {
  const Icon = status === "accepted" ? CheckCircle2 : Clock3;
  return (
    <span className={`review-badge review-${status}`}>
      <Icon size={13} aria-hidden="true" />
      {humanize(status)}
    </span>
  );
}

function cameraSnapshotUrl(
  workspaceId: number,
  cameraId: number,
  version?: string | number
) {
  const suffix = version == null ? "" : `?v=${encodeURIComponent(version)}`;
  return `/api/workspaces/${workspaceId}/cameras/${cameraId}/snapshot${suffix}`;
}

function SceneMap({
  zones,
  snapshotUrl
}: {
  zones: ZoneConfig[];
  snapshotUrl?: string;
}) {
  return (
    <figure className="scene-map">
      <svg
        viewBox="0 0 100 56"
        role="img"
        aria-label="Normalized traffic scene zone preview"
      >
        {snapshotUrl ? (
          <image
            className="scene-snapshot"
            href={snapshotUrl}
            width="100"
            height="56"
            preserveAspectRatio="none"
          />
        ) : null}
        {zones.map((zone) => (
          <polygon
            key={zone.id}
            className={`scene-zone zone-${zone.type}`}
            points={zone.points_normalized
              .map(([x, y]) => `${x * 100},${y * 56}`)
              .join(" ")}
          />
        ))}
      </svg>
      <figcaption>
        <span>Normalized zone geometry</span>
        <span>{zones.length} enabled</span>
      </figcaption>
    </figure>
  );
}

function ZoneLegend({ zones }: { zones: ZoneConfig[] }) {
  if (zones.length === 0) {
    return <p className="muted-copy">No enabled zones are available.</p>;
  }

  return (
    <div className="zone-legend">
      {zones.map((zone) => (
        <div className="legend-row" key={zone.id}>
          <span
            className={`legend-mark zone-${zone.type}`}
            aria-hidden="true"
          />
          <span>{zone.name}</span>
          <small>{humanize(zone.type)}</small>
        </div>
      ))}
    </div>
  );
}

function ZoneInventory({
  zones,
  editable = false,
  onToggle,
  onDelete
}: {
  zones: ZoneConfig[];
  editable?: boolean;
  onToggle?: (zone: ZoneConfig) => Promise<void>;
  onDelete?: (zone: ZoneConfig) => Promise<void>;
}) {
  if (zones.length === 0) {
    return <p className="muted-copy">No zones are defined in this configuration.</p>;
  }

  return (
    <div className="zone-inventory">
      {zones.map((zone) => (
        <article className="zone-inventory-row" key={zone.id}>
          <span
            className={`legend-mark zone-${zone.type}`}
            aria-hidden="true"
          />
          <div>
            <strong>{zone.name}</strong>
            <span>{zone.id}</span>
          </div>
          <dl>
            <div>
              <dt>Type</dt>
              <dd>{humanize(zone.type)}</dd>
            </div>
            <div>
              <dt>Points</dt>
              <dd>{zone.points_normalized.length}</dd>
            </div>
          </dl>
          {editable ? (
            <span className="row-actions">
              <button
                className="text-action"
                type="button"
                onClick={() => void onToggle?.(zone)}
              >
                {zone.enabled ? "Disable" : "Enable"}
              </button>
              <button
                className="icon-button subtle-danger"
                type="button"
                aria-label={`Delete ${zone.name}`}
                onClick={() => {
                  if (window.confirm(`Delete ${zone.name}?`)) {
                    void onDelete?.(zone);
                  }
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </span>
          ) : (
            <small className={zone.enabled ? "enabled-copy" : "disabled-copy"}>
              {zone.enabled ? "Enabled" : "Disabled"}
            </small>
          )}
        </article>
      ))}
    </div>
  );
}

function SourceDetails({ config }: { config: RoadLensConfig | null }) {
  if (!config) {
    return <p className="muted-copy">No camera source is available.</p>;
  }

  const [width, height] = config.camera.reference_resolution;
  const rows = [
    {
      icon: <FileVideo size={16} aria-hidden="true" />,
      label: "Source",
      value: config.camera.source_path
    },
    {
      icon: <Gauge size={16} aria-hidden="true" />,
      label: "Reference",
      value: `${width} × ${height}`
    },
    {
      icon: <Clock3 size={16} aria-hidden="true" />,
      label: "Timezone",
      value: config.camera.timezone
    }
  ];

  return (
    <dl className="detail-list">
      {rows.map((row) => (
        <div key={row.label}>
          <span className="detail-icon">{row.icon}</span>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function RuleList({
  rules,
  editable = false,
  onToggle,
  onDelete
}: {
  rules: RuleConfig[];
  editable?: boolean;
  onToggle?: (rule: RuleConfig) => Promise<void>;
  onDelete?: (rule: RuleConfig) => Promise<void>;
}) {
  if (rules.length === 0) {
    return (
      <div className="inline-empty">
        <SlidersHorizontal size={18} aria-hidden="true" />
        <span>No rules are defined in this configuration.</span>
      </div>
    );
  }

  return (
    <div className="rule-table">
      {rules.map((rule) => (
        <article className="rule-row" key={rule.id}>
          <span className={`rule-state ${rule.enabled ? "enabled" : "disabled"}`}>
            {rule.enabled ? (
              <CheckCircle2 size={15} aria-hidden="true" />
            ) : (
              <CircleDot size={15} aria-hidden="true" />
            )}
          </span>
          <div>
            <strong>{rule.name}</strong>
            <span>{rule.actions.map(humanize).join(" · ")}</span>
          </div>
          {editable ? (
            <span className="row-actions">
              <button
                className="text-action"
                type="button"
                onClick={() => void onToggle?.(rule)}
              >
                {rule.enabled ? "Disable" : "Enable"}
              </button>
              <button
                className="icon-button subtle-danger"
                type="button"
                aria-label={`Delete ${rule.name}`}
                onClick={() => {
                  if (window.confirm(`Delete ${rule.name}?`)) {
                    void onDelete?.(rule);
                  }
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </span>
          ) : (
            <small>{rule.enabled ? "Active" : "Inactive"}</small>
          )}
        </article>
      ))}
    </div>
  );
}

function PipelineProfile({ config }: { config: RoadLensConfig | null }) {
  if (!config) {
    return <p className="muted-copy">No pipeline profile is available.</p>;
  }

  const profileRows = [
    ["Motion threshold", String(config.frame_selection.motion_threshold)],
    ["Cooldown", `${config.frame_selection.cooldown_frames} frames`],
    [
      "Vehicle confidence",
      formatPercent(config.detection.vehicle_confidence)
    ],
    ["Plate confidence", formatPercent(config.detection.plate_confidence)],
    [
      "Evidence storage",
      config.storage.save_evidence_images ? "Images + records" : "Records only"
    ]
  ];

  return (
    <dl className="profile-list">
      {profileRows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function EvidenceDialog({
  evidence,
  onClose
}: {
  evidence: EvidenceItem | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={Boolean(evidence)} onOpenChange={(open) => !open && onClose()}>
      {evidence ? (
        <DialogContent className="dialog-panel">
          <DialogHeader className="dialog-header">
            <div>
              <span>Evidence #{evidence.id}</span>
              <DialogTitle>{plateLabel(evidence)}</DialogTitle>
            </div>
          </DialogHeader>

          {evidence.artifacts[0] ? (
            <figure className="evidence-artifact">
              <img
                src={evidence.artifacts[0].url}
                alt={`Evidence artifact for ${plateLabel(evidence)}`}
              />
            </figure>
          ) : (
            <div className="artifact-empty">
              <FileVideo size={20} aria-hidden="true" />
              No image artifact was saved for this event.
            </div>
          )}

          <dl className="dialog-details">
            <div>
              <dt>Rule</dt>
              <dd>{evidence.rule.name}</dd>
            </div>
            <div>
              <dt>Zone</dt>
              <dd>{evidence.zone.name}</dd>
            </div>
            <div>
              <dt>Vehicle</dt>
              <dd>{humanize(evidence.vehicle.class)}</dd>
            </div>
            <div>
              <dt>Source frame</dt>
              <dd>{evidence.source_frame_number}</dd>
            </div>
            <div>
              <dt>OCR confidence</dt>
              <dd>{formatConfidence(evidence.detections[0]?.ocr_confidence)}</dd>
            </div>
            <div>
              <dt>Review</dt>
              <dd>
                <ReviewBadge status={evidence.review_status} />
              </dd>
            </div>
          </dl>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

function DashboardSkeleton() {
  return (
    <div className="skeleton-layout" aria-label="Loading dashboard">
      <div className="skeleton-strip">
        {Array.from({ length: 4 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
      <div className="skeleton-main">
        <span />
        <span />
      </div>
    </div>
  );
}

function statusCopy(state: LoadState) {
  if (state === "ready") return "Connected and responding";
  if (state === "loading") return "Syncing current data";
  if (state === "error") return "Connection needs attention";
  return "Waiting for connection";
}

function zoneTypes(zones: ZoneConfig[]) {
  return new Set(zones.map((zone) => zone.type)).size;
}

function plateLabel(item: EvidenceItem) {
  return item.detections[0]?.plate_text || "OCR review";
}

function humanize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function slugId(value: string) {
  return (
    value
      .trim()
      .toLocaleLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "untitled"
  );
}

function initials(value: string) {
  return value
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase())
    .join("");
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("en", {
    style: "percent",
    maximumFractionDigits: 0
  }).format(value);
}

function formatConfidence(value: number | null | undefined) {
  return value == null ? "Not recorded" : formatPercent(value);
}

function formatTime(date: Date) {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatEvidenceTime(item: EvidenceItem) {
  if (item.timestamp_seconds != null) {
    return `${item.timestamp_seconds.toFixed(1)} s`;
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(item.created_at));
}

function pageFromPath(pathname: string): PageId {
  const page = pathname.split("/").filter(Boolean)[0];
  if (
    page === "evidence" ||
    page === "cameras" ||
    page === "zones" ||
    page === "rules" ||
    page === "workspace" ||
    page === "team"
  ) {
    return page;
  }
  return "overview";
}

export default Dashboard;
