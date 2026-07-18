import { LoaderCircle, ScanLine, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import Dashboard from "./Dashboard";
import "./product.css";
import "./components/ui/ui.css";

export type UserSummary = {
  id: number;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
};

export type WorkspaceSummary = {
  id: number;
  name: string;
  slug: string;
  timezone: string;
  role: "owner" | "admin" | "operator" | "viewer";
  camera_count: number;
  member_count: number;
  created_at: string;
  updated_at: string;
};

export type CameraSummary = {
  id: number;
  workspace_id: number;
  camera_key: string;
  name: string;
  source_type: "video_file" | "rtsp" | "webcam";
  source_path: string;
  timezone: string;
  enabled: boolean;
  has_source_credentials: boolean;
  reference_resolution: [number, number];
  zone_count: number;
  rule_count: number;
  active_rule_count: number;
  created_at: string;
  updated_at: string;
};

type SessionPayload = {
  authenticated: boolean;
  setup_required: boolean;
  user: UserSummary | null;
  workspaces: WorkspaceSummary[];
};

export async function productApi<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed with ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function ProductApp() {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [cameras, setCameras] = useState<CameraSummary[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<number | null>(null);
  const [activeCameraId, setActiveCameraId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSession = useCallback(async () => {
    try {
      const payload = await productApi<SessionPayload>("/api/auth/session");
      setSession(payload);
      setError(null);
      if (payload.authenticated && payload.workspaces.length > 0) {
        const stored = Number(localStorage.getItem("roadlens_workspace_id"));
        const workspace =
          payload.workspaces.find((item) => item.id === stored) ??
          payload.workspaces[0];
        setActiveWorkspaceId(workspace.id);
      } else {
        setActiveWorkspaceId(null);
      }
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "RoadLens API unavailable"
      );
    }
  }, []);

  const loadCameras = useCallback(async (workspaceId: number) => {
    const payload = await productApi<{ items: CameraSummary[] }>(
      `/api/workspaces/${workspaceId}/cameras`
    );
    setCameras(payload.items);
    const stored = Number(localStorage.getItem(`roadlens_camera_${workspaceId}`));
    const camera =
      payload.items.find((item) => item.id === stored) ?? payload.items[0] ?? null;
    setActiveCameraId(camera?.id ?? null);
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  useEffect(() => {
    if (activeWorkspaceId == null || !session?.authenticated) {
      setCameras([]);
      setActiveCameraId(null);
      return;
    }
    localStorage.setItem("roadlens_workspace_id", String(activeWorkspaceId));
    void loadCameras(activeWorkspaceId).catch((loadError) =>
      setError(loadError instanceof Error ? loadError.message : "Could not load cameras")
    );
  }, [activeWorkspaceId, loadCameras, session?.authenticated]);

  if (session == null) {
    return <ProductLoading error={error} />;
  }

  if (!session.authenticated) {
    return (
      <AuthScreen
        mode={session.setup_required ? "setup" : "login"}
        onAuthenticated={loadSession}
      />
    );
  }

  if (!session.user) {
    return <ProductLoading error="Authenticated user data is unavailable." />;
  }

  const activeWorkspace =
    session.workspaces.find((item) => item.id === activeWorkspaceId) ??
    session.workspaces[0] ??
    null;
  const activeCamera =
    cameras.find((item) => item.id === activeCameraId) ?? cameras[0] ?? null;

  return (
    <Dashboard
      user={session.user}
      workspaces={session.workspaces}
      activeWorkspace={activeWorkspace}
      cameras={cameras}
      activeCamera={activeCamera}
      onWorkspaceChange={setActiveWorkspaceId}
      onCameraChange={(cameraId) => {
        setActiveCameraId(cameraId);
        if (activeWorkspace) {
          localStorage.setItem(
            `roadlens_camera_${activeWorkspace.id}`,
            String(cameraId)
          );
        }
      }}
      onProductChange={async () => {
        await loadSession();
        if (activeWorkspaceId != null) {
          await loadCameras(activeWorkspaceId);
        }
      }}
      onLogout={async () => {
        await productApi<void>("/api/auth/logout", { method: "POST" });
        setSession(null);
        setCameras([]);
        await loadSession();
      }}
    />
  );
}

function ProductLoading({ error }: { error: string | null }) {
  return (
    <main className="auth-shell">
      <section className="auth-card auth-loading" aria-live="polite">
        <span className="auth-brand-mark" aria-hidden="true">
          {error ? <ShieldCheck size={22} /> : <LoaderCircle size={22} />}
        </span>
        <h1>{error ? "RoadLens needs attention" : "Loading RoadLens"}</h1>
        <p>{error ?? "Checking your workspace and secure session."}</p>
      </section>
    </main>
  );
}

function AuthScreen({
  mode,
  onAuthenticated
}: {
  mode: "setup" | "login";
  onAuthenticated: () => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);

    try {
      if (mode === "setup") {
        await productApi("/api/auth/setup", {
          method: "POST",
          body: JSON.stringify({
            name: form.get("name"),
            email: form.get("email"),
            password: form.get("password"),
            workspace_name: form.get("workspace_name"),
            timezone: form.get("timezone")
          })
        });
      } else {
        await productApi("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({
            email: form.get("email"),
            password: form.get("password")
          })
        });
      }
      await onAuthenticated();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Authentication failed"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="auth-shell">
      <div className="auth-frame">
        <section className="auth-card">
          <header>
            <span className="auth-brand">
            <span className="auth-brand-mark" aria-hidden="true">
              <ScanLine size={20} />
            </span>
              <strong>RoadLens</strong>
          </span>
            <h2>
              {mode === "setup" ? "Create workspace" : "Sign in"}
            </h2>
          </header>
          <form onSubmit={submit}>
            {mode === "setup" ? (
              <>
                <Label>
                  Your name
                  <Input name="name" autoComplete="name" required minLength={2} />
                </Label>
                <Label>
                  Workspace name
                  <Input name="workspace_name" required minLength={2} />
                </Label>
                <Label>
                  Workspace timezone
                  <Input name="timezone" defaultValue="Asia/Kathmandu" required />
                </Label>
              </>
            ) : null}
            <Label>
              Email
              <Input name="email" type="email" autoComplete="email" required />
            </Label>
            <Label>
              Password
              <Input
                name="password"
                type="password"
                autoComplete={mode === "setup" ? "new-password" : "current-password"}
                required
                minLength={8}
              />
            </Label>
            {error ? <p className="form-error">{error}</p> : null}
            <Button
              className="auth-submit"
              type="submit"
              disabled={submitting}
              data-state={submitting ? "loading" : undefined}
            >
              {submitting ? <LoaderCircle size={16} aria-hidden="true" /> : null}
              {submitting
                ? "Please wait"
                : mode === "setup"
                  ? "Create workspace"
                  : "Sign in"}
            </Button>
          </form>
        </section>
      </div>
    </main>
  );
}

export default ProductApp;
