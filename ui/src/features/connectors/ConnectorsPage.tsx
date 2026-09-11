import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import {
  api,
  type BrowseContainer,
  type ConnectorConnection,
  type TestConnectionResult,
} from "@/lib/api-client";

const SOURCE_LABELS: Record<string, string> = {
  azure_devops: "Azure DevOps",
  github: "GitHub",
  confluence: "Confluence",
  jira: "Jira",
  teams: "Microsoft Teams",
};

function TestResultBanner({ result }: { result: TestConnectionResult }) {
  return (
    <div
      className={`rounded p-3 text-sm ${
        result.success ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
      }`}
    >
      <div className="font-medium">{result.success ? "✓ Connection succeeded" : "✗ Connection failed"}</div>
      <div>{result.message}</div>
      {result.containers.length > 0 && (
        <div className="mt-1 text-xs">Found: {result.containers.join(", ")}</div>
      )}
      <div className="mt-1 text-xs text-neutral-500">{result.duration_seconds}s</div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-xs text-neutral-600">
      <span className="font-medium text-neutral-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-neutral-500">{hint}</span>}
    </label>
  );
}

function ContainerPicker({
  label,
  browseResult,
  browsePending,
  browseError,
  currentCount,
  selected,
  onBrowse,
  onToggle,
}: {
  label: string;
  browseResult: BrowseContainer[] | null;
  browsePending: boolean;
  browseError: string | null;
  currentCount: number | null;
  selected: string[];
  onBrowse: () => void;
  onToggle: (nativeId: string) => void;
}) {
  return (
    <div className="rounded border border-neutral-200 p-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium text-neutral-700">Which {label} to sync</div>
        <button
          type="button"
          onClick={onBrowse}
          disabled={browsePending}
          className="rounded border border-neutral-400 px-2 py-1 text-xs disabled:opacity-50"
        >
          {browsePending ? "Browsing…" : `Browse ${label}`}
        </button>
      </div>
      {browseResult === null && (
        <div className="mt-1 text-xs text-neutral-500">
          {currentCount === null
            ? `Currently syncing every ${label.slice(0, -1)} the credential can see.`
            : `${currentCount} ${label} currently selected.`}{" "}
          Browse to see and change the list.
        </div>
      )}
      {browseError && <div className="mt-1 text-xs text-red-600">{browseError}</div>}
      {browseResult !== null && browseResult.length === 0 && (
        <div className="mt-1 text-xs text-amber-600">
          No {label} found — either none exist, or the credential's scope doesn't cover them.
        </div>
      )}
      {browseResult !== null && browseResult.length > 0 && (
        <div className="mt-2 max-h-40 space-y-0.5 overflow-auto">
          {browseResult.map((c) => (
            <label key={c.native_id} className="flex items-center gap-2 text-xs text-neutral-600">
              <input
                type="checkbox"
                checked={selected.includes(c.native_id)}
                onChange={() => onToggle(c.native_id)}
              />
              {c.name}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectorDetailPanel({
  connection,
  onSaved,
  onDeleted,
}: {
  connection: ConnectorConnection | null;
  onSaved: (savedId: string) => void;
  onDeleted: () => void;
}) {
  const isNew = connection === null;
  const queryClient = useQueryClient();

  const [sourceSystem, setSourceSystem] = useState(connection?.source_system ?? "azure_devops");
  const [instanceId, setInstanceId] = useState(connection?.instance_id ?? "");
  const [displayName, setDisplayName] = useState(connection?.display_name ?? "");
  const [mode, setMode] = useState<"fixture" | "live">((connection?.mode as "fixture" | "live") ?? "live");
  const [orgUrl, setOrgUrl] = useState(String(connection?.config.org_url ?? ""));
  const [org, setOrg] = useState(String(connection?.config.org ?? ""));
  const [repoVisibility, setRepoVisibility] = useState(
    String(connection?.config.repo_visibility ?? "all")
  );
  const [siteUrl, setSiteUrl] = useState(String(connection?.config.site_url ?? ""));
  const [email, setEmail] = useState(String(connection?.config.email ?? ""));
  const [tenantId, setTenantId] = useState(String(connection?.config.tenant_id ?? ""));
  const [teamId, setTeamId] = useState(String(connection?.config.team_id ?? ""));
  const [clientId, setClientId] = useState(String(connection?.config.client_id ?? ""));
  const [credential, setCredential] = useState("");
  const [entityTypes, setEntityTypes] = useState<string[]>(
    Array.isArray(connection?.config.entity_types) ? (connection!.config.entity_types as string[]) : []
  );
  const savedContainers = Array.isArray(connection?.config.selected_containers)
    ? (connection!.config.selected_containers as string[])
    : null;
  const [selectedContainers, setSelectedContainers] = useState<string[]>(savedContainers ?? []);
  const [containersTouched, setContainersTouched] = useState(false);
  const [browseResult, setBrowseResult] = useState<BrowseContainer[] | null>(null);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);

  const entityTypesQuery = useQuery({ queryKey: ["entity-types"], queryFn: api.listEntityTypes });
  const availableEntityTypes = entityTypesQuery.data?.[sourceSystem] ?? {};
  const containerLabel =
    sourceSystem === "azure_devops" || sourceSystem === "jira"
      ? "projects"
      : sourceSystem === "confluence"
        ? "spaces"
        : sourceSystem === "teams"
          ? "channels"
          : "repositories";
  const runsQuery = useQuery({
    queryKey: ["sync-runs", connection?.id],
    queryFn: () => api.listSyncRuns(connection!.id),
    enabled: false,
  });

  const connectionProperties = (): Record<string, unknown> => {
    if (sourceSystem === "azure_devops") return { org_url: orgUrl };
    if (sourceSystem === "confluence" || sourceSystem === "jira") return { site_url: siteUrl, email };
    if (sourceSystem === "teams") return { tenant_id: tenantId, team_id: teamId, client_id: clientId };
    return { org, repo_visibility: repoVisibility };
  };

  const localConfig = () => ({
    ...connectionProperties(),
    entity_types: entityTypes,
    ...(containersTouched ? { selected_containers: selectedContainers } : {}),
  });

  const toggleEntityType = (key: string) => {
    setEntityTypes((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
    setTestResult(null);
  };
  const toggleContainer = (nativeId: string) => {
    setSelectedContainers((prev) =>
      prev.includes(nativeId) ? prev.filter((c) => c !== nativeId) : [...prev, nativeId]
    );
  };

  const test = useMutation({
    mutationFn: () =>
      isNew
        ? api.testConnection({
            source_system: sourceSystem,
            mode,
            config: mode === "live" ? localConfig() : {},
            credential: mode === "live" ? credential : undefined,
          })
        : api.testExistingConnection(connection.id),
    onSuccess: setTestResult,
  });

  const browse = useMutation({
    mutationFn: () =>
      isNew
        ? api.browseConnector({
            source_system: sourceSystem,
            mode,
            config: connectionProperties(),
            credential,
          })
        : api.browseExistingConnection(connection.id),
    onSuccess: (res) => {
      setBrowseResult(res.containers);
      setSelectedContainers(res.containers.map((c) => c.native_id));
      setContainersTouched(true);
    },
  });

  const sync = useMutation({
    mutationFn: () => api.triggerSync(connection!.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["connectors"] }),
  });

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const deleteConnection = useMutation({
    mutationFn: () => api.deleteConnector(connection!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
      onDeleted();
    },
  });

  const create = useMutation({
    mutationFn: () =>
      api.createConnector({
        source_system: sourceSystem,
        instance_id: instanceId,
        display_name: displayName || instanceId,
        mode,
        config: mode === "live" ? localConfig() : {},
        credential: mode === "live" ? credential : undefined,
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
      onSaved(res.id);
    },
  });

  const save = useMutation({
    mutationFn: () => api.updateConnectorConfig(connection!.id, localConfig(), displayName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
      onSaved(connection!.id);
    },
  });

  const canTest = mode === "fixture" || (isNew ? !!credential : true);

  return (
    <div className="space-y-4 rounded border border-neutral-200 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">
          {isNew ? "New connection" : connection.display_name}
        </div>
        {!isNew && (
          <div className="flex items-center gap-2">
            <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-500">
              {SOURCE_LABELS[connection.source_system] ?? connection.source_system} /{" "}
              {connection.instance_id} · {connection.mode}
            </span>
            {confirmingDelete ? (
              <span className="flex items-center gap-1 text-xs">
                <span className="text-neutral-500">
                  Delete? (already-synced assets stay in the catalog)
                </span>
                <button
                  onClick={() => deleteConnection.mutate()}
                  disabled={deleteConnection.isPending}
                  className="rounded bg-red-600 px-2 py-0.5 text-white disabled:opacity-50"
                >
                  {deleteConnection.isPending ? "Deleting…" : "Yes, delete"}
                </button>
                <button
                  onClick={() => setConfirmingDelete(false)}
                  className="rounded border border-neutral-300 px-2 py-0.5"
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                onClick={() => setConfirmingDelete(true)}
                className="text-xs text-red-600 hover:underline"
              >
                Delete
              </button>
            )}
          </div>
        )}
      </div>
      {deleteConnection.isError && (
        <div className="text-sm text-red-600">{(deleteConnection.error as Error).message}</div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {isNew ? (
          <>
            <Field label="Source system">
              <select
                value={sourceSystem}
                onChange={(e) => {
                  setSourceSystem(e.target.value);
                  setTestResult(null);
                  setBrowseResult(null);
                  setContainersTouched(false);
                }}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              >
                <option value="azure_devops">Azure DevOps</option>
                <option value="github">GitHub</option>
                <option value="confluence">Confluence</option>
                <option value="jira">Jira</option>
                <option value="teams">Microsoft Teams</option>
              </select>
            </Field>
            <Field label="Mode">
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as "fixture" | "live")}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              >
                <option value="live">live (real connection)</option>
                <option value="fixture">fixture (sample data)</option>
              </select>
            </Field>
            <Field label="Instance id">
              <input
                value={instanceId}
                onChange={(e) => setInstanceId(e.target.value)}
                placeholder="ado-acme"
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              />
            </Field>
          </>
        ) : null}
        <Field label="Display name">
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          />
        </Field>
      </div>

      {mode === "live" && sourceSystem === "azure_devops" && (
        <div className="grid grid-cols-2 gap-3 rounded bg-amber-50 p-3">
          <Field
            label="Organization URL"
            hint='The org root only — no project name. A trailing project segment is stripped automatically if pasted from the browser.'
          >
            <input
              placeholder="https://dev.azure.com/your-org"
              value={orgUrl}
              onChange={(e) => {
                setOrgUrl(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          {isNew && (
            <Field label="Personal access token">
              <input
                type="password"
                value={credential}
                onChange={(e) => {
                  setCredential(e.target.value);
                  setTestResult(null);
                  setBrowseResult(null);
                }}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              />
            </Field>
          )}
          <div className="col-span-2 text-xs text-neutral-500">
            Scopes needed depend on what's selected below: <strong>Work Items (Read)</strong> for
            work items, <strong>Code (Read)</strong> for Git Repos and Pull Requests,{" "}
            <strong>Wiki (Read)</strong> for wiki pages. A missing scope doesn't error — the
            matching endpoint just silently returns nothing.
            {!isNew && " The stored token isn't shown or editable here — recreate the connection to rotate it."}
          </div>
        </div>
      )}

      {mode === "live" && sourceSystem === "github" && (
        <div className="grid grid-cols-2 gap-3 rounded bg-amber-50 p-3">
          <Field
            label="Organization or user login"
            hint="Just the login, not a URL — a repo or org page URL pasted here has its login extracted automatically. Works for both organizations and personal accounts."
          >
            <input
              placeholder="acme-org"
              value={org}
              onChange={(e) => {
                setOrg(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field
            label="Repo visibility"
            hint="Only applies when browsing your own personal account — org repo listing already includes every repo the token can see."
          >
            <select
              value={repoVisibility}
              onChange={(e) => setRepoVisibility(e.target.value)}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            >
              <option value="all">All (public + private)</option>
              <option value="public">Public only</option>
              <option value="private">Private only</option>
            </select>
          </Field>
          {isNew && (
            <Field label="Personal access token">
              <input
                type="password"
                value={credential}
                onChange={(e) => {
                  setCredential(e.target.value);
                  setTestResult(null);
                  setBrowseResult(null);
                }}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              />
            </Field>
          )}
          <div className="col-span-2 text-xs text-neutral-500">
            Needs repo (read) scope for Issues/PRs/repos (including private, if selected above),
            and read:project for Projects (v2).
            {!isNew && " The stored token isn't shown or editable here — recreate the connection to rotate it."}
          </div>
        </div>
      )}

      {mode === "live" && sourceSystem === "confluence" && (
        <div className="grid grid-cols-2 gap-3 rounded bg-amber-50 p-3">
          <Field
            label="Site URL"
            hint='The site root only — no space or page path. A trailing "/wiki/..." path is stripped automatically if pasted from the browser.'
          >
            <input
              placeholder="https://acme.atlassian.net"
              value={siteUrl}
              onChange={(e) => {
                setSiteUrl(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field label="Account email">
            <input
              placeholder="you@acme.example"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          {isNew && (
            <Field label="API token">
              <input
                type="password"
                value={credential}
                onChange={(e) => {
                  setCredential(e.target.value);
                  setTestResult(null);
                  setBrowseResult(null);
                }}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              />
            </Field>
          )}
          <div className="col-span-2 text-xs text-neutral-500">
            Create an API token at id.atlassian.com → Security → API tokens. Auth is Basic
            (email + token), not just a bare token — both fields above are required.
            {!isNew && " The stored token isn't shown or editable here — recreate the connection to rotate it."}
          </div>
        </div>
      )}

      {mode === "live" && sourceSystem === "jira" && (
        <div className="grid grid-cols-2 gap-3 rounded bg-amber-50 p-3">
          <Field
            label="Site URL"
            hint='The site root only — no project or issue path. A trailing "/browse/..." path is stripped automatically if pasted from the browser.'
          >
            <input
              placeholder="https://acme.atlassian.net"
              value={siteUrl}
              onChange={(e) => {
                setSiteUrl(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field label="Account email">
            <input
              placeholder="you@acme.example"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          {isNew && (
            <Field label="API token">
              <input
                type="password"
                value={credential}
                onChange={(e) => {
                  setCredential(e.target.value);
                  setTestResult(null);
                  setBrowseResult(null);
                }}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              />
            </Field>
          )}
          <div className="col-span-2 text-xs text-neutral-500">
            Create an API token at id.atlassian.com → Security → API tokens — the same kind of
            token used for Confluence, though this connection stores its own copy. Auth is Basic
            (email + token), not just a bare token — both fields above are required.
            {!isNew && " The stored token isn't shown or editable here — recreate the connection to rotate it."}
          </div>
        </div>
      )}

      {mode === "live" && sourceSystem === "teams" && (
        <div className="grid grid-cols-2 gap-3 rounded bg-amber-50 p-3">
          <Field label="Tenant ID" hint="Your Microsoft Entra (Azure AD) tenant id, not a domain name.">
            <input
              placeholder="00000000-0000-0000-0000-000000000000"
              value={tenantId}
              onChange={(e) => {
                setTenantId(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field label="Team ID" hint="The Microsoft Teams team this connection covers — one connection per team.">
            <input
              placeholder="00000000-0000-0000-0000-000000000000"
              value={teamId}
              onChange={(e) => {
                setTeamId(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field label="App (client) ID" hint="From your Entra app registration.">
            <input
              placeholder="00000000-0000-0000-0000-000000000000"
              value={clientId}
              onChange={(e) => {
                setClientId(e.target.value);
                setTestResult(null);
                setBrowseResult(null);
              }}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </Field>
          {isNew && (
            <Field label="Client secret">
              <input
                type="password"
                value={credential}
                onChange={(e) => {
                  setCredential(e.target.value);
                  setTestResult(null);
                  setBrowseResult(null);
                }}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
              />
            </Field>
          )}
          <div className="col-span-2 text-xs text-neutral-500">
            Needs an Entra app registration with the <strong>application</strong> (not delegated)
            Graph permissions ChannelMessage.Read.All, Channel.ReadBasic.All, and
            Team.ReadBasic.All, admin-consented. Auth is OAuth2 client-credentials — the app's
            client secret is stored as this connection's credential.
            {!isNew && " The stored secret isn't shown or editable here — recreate the connection to rotate it."}
          </div>
        </div>
      )}

      {mode === "live" && Object.keys(availableEntityTypes).length > 0 && (
        <div className="rounded border border-neutral-200 p-3">
          <div className="text-xs font-medium text-neutral-700">
            What to pull — pick which technical asset types this connection syncs
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1">
            {Object.entries(availableEntityTypes).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-xs text-neutral-600">
                <input
                  type="checkbox"
                  checked={entityTypes.includes(key)}
                  onChange={() => toggleEntityType(key)}
                />
                {label}
              </label>
            ))}
          </div>
          {entityTypes.length === 0 && (
            <div className="mt-2 text-xs text-amber-600">
              Nothing selected — sync will find containers but pull no objects.
            </div>
          )}
        </div>
      )}

      {mode === "live" && (isNew ? credential : true) && (
        <ContainerPicker
          label={containerLabel}
          browseResult={browseResult}
          browsePending={browse.isPending}
          browseError={browse.isError ? (browse.error as Error).message : null}
          currentCount={containersTouched ? selectedContainers.length : savedContainers?.length ?? null}
          selected={selectedContainers}
          onBrowse={() => browse.mutate()}
          onToggle={(id) => {
            setContainersTouched(true);
            toggleContainer(id);
          }}
        />
      )}

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => test.mutate()}
          disabled={test.isPending || !canTest}
          className="rounded border border-neutral-400 px-3 py-1.5 text-sm disabled:opacity-50"
        >
          {test.isPending ? "Testing…" : "Test connection"}
        </button>
        {isNew ? (
          <button
            type="button"
            onClick={() => create.mutate()}
            disabled={create.isPending || !instanceId || (mode === "live" && !credential)}
            className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {create.isPending ? "Creating…" : "Create connection"}
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {save.isPending ? "Saving…" : "Save changes"}
            </button>
            <button
              type="button"
              onClick={() => sync.mutate()}
              disabled={sync.isPending}
              className="rounded border border-neutral-400 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {sync.isPending ? "Syncing…" : "Sync now"}
            </button>
            <button
              type="button"
              onClick={() => runsQuery.refetch()}
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm"
            >
              History
            </button>
          </>
        )}
      </div>

      {!isNew && (
        <div className="text-xs text-neutral-400">
          Changing connection properties, entity types, or the sync list above requires{" "}
          <strong>Save changes</strong> before Test/Sync reflect them.
        </div>
      )}

      {testResult && <TestResultBanner result={testResult} />}
      {create.isError && <div className="text-sm text-red-600">{(create.error as Error).message}</div>}
      {save.isError && <div className="text-sm text-red-600">{(save.error as Error).message}</div>}

      {sync.data && (
        <div className="rounded bg-neutral-50 p-3 text-sm">
          <span
            className={`font-medium ${sync.data.status === "SUCCEEDED" ? "text-green-700" : "text-red-700"}`}
          >
            {sync.data.status}
          </span>{" "}
          in {sync.data.duration_seconds}s — {sync.data.nodes_upserted} nodes upserted,{" "}
          {sync.data.nodes_tombstoned} tombstoned, {sync.data.edges_created} edges created
          {sync.data.error_detail && (
            <div className="mt-1 text-red-600">
              {sync.data.error_category}: {sync.data.error_detail}
            </div>
          )}
        </div>
      )}

      {runsQuery.data && (
        <table className="w-full text-left text-xs">
          <thead className="text-neutral-500">
            <tr>
              <th className="py-1">Started</th>
              <th>Status</th>
              <th>Nodes</th>
              <th>Edges</th>
            </tr>
          </thead>
          <tbody>
            {runsQuery.data.map((run) => (
              <tr key={run.id} className="border-t border-neutral-100">
                <td className="py-1">{new Date(run.started_at).toLocaleString()}</td>
                <td>{run.status}</td>
                <td>{run.nodes_upserted}</td>
                <td>{run.edges_created}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function ConnectorsPage() {
  const connectionsQuery = useQuery({ queryKey: ["connectors"], queryFn: api.listConnectors });
  const [selectedId, setSelectedId] = useState<string | "new" | null>(null);

  const selectedConnection =
    selectedId && selectedId !== "new"
      ? connectionsQuery.data?.find((c) => c.id === selectedId) ?? null
      : null;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Connectors</h1>

      <div className="grid grid-cols-5 gap-6">
        <div className="col-span-2 rounded border border-neutral-200 p-2">
          <button
            onClick={() => setSelectedId("new")}
            className={`mb-1 flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm font-medium ${
              selectedId === "new" ? "bg-neutral-900 text-white" : "border border-dashed border-neutral-300 text-neutral-600 hover:bg-neutral-50"
            }`}
          >
            + New connection
          </button>
          {connectionsQuery.isLoading && <div className="p-2 text-sm text-neutral-500">Loading…</div>}
          {connectionsQuery.data?.map((c) => (
            <div
              key={c.id}
              onClick={() => setSelectedId(c.id)}
              className={`cursor-pointer rounded px-3 py-2 ${
                selectedId === c.id ? "bg-neutral-900 text-white" : "hover:bg-neutral-50"
              }`}
            >
              <div className="text-sm font-medium">{c.display_name}</div>
              <div className={`text-xs ${selectedId === c.id ? "text-white/70" : "text-neutral-400"}`}>
                {SOURCE_LABELS[c.source_system] ?? c.source_system} / {c.instance_id} · {c.mode}
              </div>
            </div>
          ))}
          {connectionsQuery.data?.length === 0 && (
            <div className="p-2 text-xs text-neutral-400">No connections yet — start with one above.</div>
          )}
        </div>

        <div className="col-span-3">
          {selectedId === null && (
            <div className="flex h-full items-center justify-center rounded border border-dashed border-neutral-300 p-8 text-sm text-neutral-400">
              Select a connection to see its details, or start a new one.
            </div>
          )}
          {selectedId === "new" && (
            <ConnectorDetailPanel
              key="new"
              connection={null}
              onSaved={(id) => setSelectedId(id)}
              onDeleted={() => setSelectedId(null)}
            />
          )}
          {selectedConnection && (
            <ConnectorDetailPanel
              key={selectedConnection.id}
              connection={selectedConnection}
              onSaved={(id) => setSelectedId(id)}
              onDeleted={() => setSelectedId(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
