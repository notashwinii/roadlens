import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  KeyRound,
  LoaderCircle,
  ScanLine,
  ShieldCheck
} from "lucide-react";
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
  mfa_enabled: boolean;
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
    throw new ProductApiError(
      payload?.detail ?? `Request failed with ${response.status}`,
      response.status
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export class ProductApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ProductApiError";
    this.status = status;
  }
}

type AuthRoute = "login" | "forgot" | "reset" | "invitation";

function currentAuthRoute(): AuthRoute {
  if (window.location.pathname === "/forgot-password") return "forgot";
  if (window.location.pathname === "/reset-password") return "reset";
  if (window.location.pathname === "/accept-invitation") return "invitation";
  return "login";
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
  const [route, setRoute] = useState<AuthRoute>(currentAuthRoute);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [mfaRequired, setMfaRequired] = useState(false);
  const [ssoConfig, setSsoConfig] = useState<{
    enabled: boolean;
    provider_name: string | null;
  } | null>(null);
  const [invitation, setInvitation] = useState<{
    email: string;
    name: string;
    role: string;
    workspace_name: string;
    existing_account: boolean;
    mfa_required: boolean;
  } | null>(null);
  const token = new URLSearchParams(window.location.search).get("token") ?? "";

  useEffect(() => {
    const onPopState = () => {
      setRoute(currentAuthRoute());
      setError(null);
      setSuccess(null);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (route !== "invitation" || !token) return;
    setInvitation(null);
    setError(null);
    void productApi<typeof invitation>(`/api/invitations/${token}`)
      .then(setInvitation)
      .catch((loadError) =>
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Could not load invitation"
        )
      );
  }, [route, token]);

  useEffect(() => {
    if (route !== "login" || mode === "setup") return;
    void productApi<{
      enabled: boolean;
      provider_name: string | null;
    }>("/api/auth/sso/config")
      .then(setSsoConfig)
      .catch(() => setSsoConfig({ enabled: false, provider_name: null }));

    const url = new URL(window.location.href);
    const ssoError = url.searchParams.get("sso_error");
    if (ssoError) {
      setError(
        "Single sign-on failed. Try again or sign in with your password."
      );
      url.searchParams.delete("sso_error");
      window.history.replaceState(
        {},
        "",
        `${url.pathname}${url.search}${url.hash}`
      );
    }
  }, [mode, route]);

  const navigate = (next: AuthRoute) => {
    const path =
      next === "forgot"
        ? "/forgot-password"
        : next === "login"
          ? "/"
          : window.location.pathname;
    window.history.pushState({}, "", path);
    setRoute(next);
    setError(null);
    setSuccess(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);

    try {
      if (route === "forgot") {
        const result = await productApi<{ message: string }>(
          "/api/auth/password-reset/request",
          {
            method: "POST",
            body: JSON.stringify({ email: form.get("email") })
          }
        );
        setSuccess(result.message);
      } else if (route === "reset") {
        const result = await productApi<{ message: string }>(
          "/api/auth/password-reset/confirm",
          {
            method: "POST",
            body: JSON.stringify({
              token,
              password: form.get("password")
            })
          }
        );
        window.history.replaceState({}, "", "/");
        setRoute("login");
        setSuccess(result.message);
      } else if (route === "invitation") {
        await productApi("/api/auth/invitations/accept", {
          method: "POST",
          body: JSON.stringify({
            token,
            password: form.get("password"),
            mfa_code: invitation?.mfa_required ? form.get("mfa_code") : null
          })
        });
        await onAuthenticated();
      } else if (mode === "setup") {
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
            password: form.get("password"),
            mfa_code: mfaRequired ? form.get("mfa_code") : null
          })
        });
        setMfaRequired(false);
      }
      if (route === "login") {
        await onAuthenticated();
      }
    } catch (submitError) {
      if (
        submitError instanceof ProductApiError &&
        submitError.status === 428
      ) {
        setMfaRequired(true);
        setError(null);
        return;
      }
      setError(
        submitError instanceof Error ? submitError.message : "Authentication failed"
      );
    } finally {
      setSubmitting(false);
    }
  };

  const isSetup = mode === "setup" && route === "login";
  const title =
    route === "forgot"
      ? "Reset password"
      : route === "reset"
        ? "Choose a new password"
        : route === "invitation"
          ? invitation
            ? `Join ${invitation.workspace_name}`
            : "Open invitation"
          : isSetup
            ? "Create workspace"
            : mfaRequired
              ? "Verify it’s you"
              : "Sign in";

  return (
    <main className="auth-shell">
      <div className="auth-frame">
        <section className="auth-card">
          <header>
            <span className="auth-brand">
              <span className="auth-brand-mark" aria-hidden="true">
                {mfaRequired ? <KeyRound size={20} /> : <ScanLine size={20} />}
              </span>
              <strong>RoadLens</strong>
            </span>
            <h2>{title}</h2>
            {route === "invitation" && invitation ? (
              <p className="auth-intro">
                {invitation.name}, you’ve been invited as {invitation.role}.
              </p>
            ) : null}
          </header>
          <form onSubmit={submit}>
            {success ? (
              <div className="form-success" role="status">
                <CheckCircle2 size={17} aria-hidden="true" />
                <span>{success}</span>
              </div>
            ) : null}
            {isSetup ? (
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
            {route === "login" || route === "forgot" ? (
              <Label>
                Email
                <Input name="email" type="email" autoComplete="email" required />
              </Label>
            ) : null}
            {route !== "forgot" && (route !== "invitation" || invitation) ? (
              <Label>
                {route === "invitation" && invitation?.existing_account
                  ? "Your RoadLens password"
                  : route === "reset" || route === "invitation" || isSetup
                    ? "Password"
                    : "Password"}
                <Input
                  name="password"
                  type="password"
                  autoComplete={
                    route === "reset" ||
                    (route === "invitation" && !invitation?.existing_account) ||
                    isSetup
                      ? "new-password"
                      : "current-password"
                  }
                  required
                  minLength={8}
                />
              </Label>
            ) : null}
            {mfaRequired && route === "login" ? (
              <Label>
                Authentication or recovery code
                <Input
                  name="mfa_code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  autoFocus
                />
              </Label>
            ) : null}
            {route === "invitation" && invitation?.mfa_required ? (
              <Label>
                Authentication or recovery code
                <Input
                  name="mfa_code"
                  autoComplete="one-time-code"
                  required
                />
              </Label>
            ) : null}
            {error ? <p className="form-error">{error}</p> : null}
            {route !== "invitation" || invitation ? (
              <Button
                className="auth-submit"
                type="submit"
                disabled={submitting || (route === "forgot" && success != null)}
                data-state={submitting ? "loading" : undefined}
              >
                {submitting ? <LoaderCircle size={16} aria-hidden="true" /> : null}
                {submitting
                  ? "Please wait"
                  : route === "forgot"
                    ? success
                      ? "Email sent"
                      : "Send reset link"
                    : route === "reset"
                      ? "Update password"
                      : route === "invitation"
                        ? "Accept invitation"
                        : isSetup
                          ? "Create workspace"
                          : mfaRequired
                            ? "Verify and sign in"
                            : "Sign in"}
              </Button>
            ) : null}
          </form>
          {route === "login" &&
          !isSetup &&
          !mfaRequired &&
          ssoConfig?.enabled ? (
            <div className="auth-sso">
              <span>or</span>
              <Button
                className="auth-sso-button"
                type="button"
                variant="outline"
                onClick={() => window.location.assign("/api/auth/sso/login")}
              >
                <Building2 size={16} aria-hidden="true" />
                Continue with {ssoConfig.provider_name ?? "SSO"}
              </Button>
            </div>
          ) : null}
          {!isSetup ? (
            <footer className="auth-footer">
              {route === "login" && !mfaRequired ? (
                <button type="button" onClick={() => navigate("forgot")}>
                  Forgot password?
                </button>
              ) : route !== "login" ? (
                <button type="button" onClick={() => navigate("login")}>
                  <ArrowLeft size={14} aria-hidden="true" />
                  Back to sign in
                </button>
              ) : null}
            </footer>
          ) : null}
        </section>
      </div>
    </main>
  );
}

export default ProductApp;
