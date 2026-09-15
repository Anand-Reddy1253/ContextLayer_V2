export interface ConnectorConnection {
  id: string;
  source_system: string;
  instance_id: string;
  display_name: string;
  mode: "fixture" | "live";
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SyncRun {
  id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  nodes_upserted: number;
  nodes_tombstoned: number;
  edges_created: number;
  error_category: string | null;
  error_detail: string | null;
}

export interface SyncTriggerResult {
  run_id: string;
  status: string;
  nodes_upserted: number;
  nodes_tombstoned: number;
  edges_created: number;
  duration_seconds: number;
  error_category: string | null;
  error_detail: string | null;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
  containers: string[];
  duration_seconds: number;
  error_category: string | null;
}

export interface BrowseContainer {
  native_id: string;
  name: string;
}

export interface CatalogNode {
  id: string;
  layer: string;
  kind: string;
  capability: string | null;
  name: string;
  description: string | null;
  source_system: string | null;
  source_instance_id: string | null;
  native_id: string | null;
  parent_id: string | null;
  path: string;
  status: string;
  deleted_at: string | null;
  attributes: Record<string, unknown>;
}

export interface CatalogEdge {
  id: string;
  src_id: string;
  dst_id: string;
  type: string;
  origin: string;
  state: string;
  confidence: number | null;
  evidence: string | null;
}

export interface ProposedEdge {
  edge: CatalogEdge;
  src: CatalogNode | null;
  dst: CatalogNode | null;
}

export interface CatalogNodeLink {
  edge: CatalogEdge;
  direction: "outgoing" | "incoming";
  node: CatalogNode | null;
}

export interface CatalogGraph {
  nodes: CatalogNode[];
  edges: CatalogEdge[];
}

export interface NativeCall {
  tool: string;
  params: Record<string, unknown>;
}

export interface CatalogLocator {
  source_system: string | null;
  source_instance_id: string | null;
  native_id: string | null;
  kind: string;
  url: string | null;
  native_call: NativeCall | null;
}

export interface SearchCardAncestor {
  node: CatalogNode;
  locator: CatalogLocator;
}

export interface SearchCardLink {
  edge: CatalogEdge;
  direction: "outgoing" | "incoming";
  node: CatalogNode;
  locator: CatalogLocator;
}

export interface SearchCardBusinessContext {
  business_node_id: string;
  business_node_name: string;
  attributes: BusinessNode["attributes"];
}

export interface SearchCard {
  node: CatalogNode;
  locator: CatalogLocator;
  score: number;
  ancestors: SearchCardAncestor[];
  links: SearchCardLink[];
  business_context: SearchCardBusinessContext | null;
}

export interface CommunicationChannel {
  platform: string;
  channel: string;
  url?: string;
}

export interface BusinessNode {
  id: string;
  parent_id: string | null;
  kind: string;
  name: string;
  description: string | null;
  owners: string[];
  path: string;
  attributes: {
    criticality_tier?: string;
    compliance_scope?: string[];
    stakeholders?: string[];
    communication_channel?: CommunicationChannel;
    [key: string]: unknown;
  };
}

export interface Binding {
  id: string;
  capability: string;
  source_system: string;
  source_instance_id: string;
  native_container: string;
  priority: number;
}

export interface ContextSpace {
  id: string;
  name: string;
  description: string;
  owners: string[];
  product: string | null;
  teams: string[];
  services: string[];
  status: string;
  business_node_id: string;
  bindings: Binding[];
}

export interface ReconcileResult {
  context_space_id: string;
  all_resolved: boolean;
  results: {
    binding_id: string;
    capability: string;
    source_system: string;
    native_container: string;
    resolved: boolean;
    node_id: string | null;
  }[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  listConnectors: () => request<ConnectorConnection[]>("/connectors"),
  listEntityTypes: () => request<Record<string, Record<string, string>>>("/connectors/entity-types"),
  createConnector: (body: {
    source_system: string;
    instance_id: string;
    display_name: string;
    mode: "fixture" | "live";
    config: Record<string, unknown>;
    credential?: string;
  }) => request<ConnectorConnection>("/connectors", { method: "POST", body: JSON.stringify(body) }),
  testConnection: (body: {
    source_system: string;
    mode: "fixture" | "live";
    config: Record<string, unknown>;
    credential?: string;
  }) => request<TestConnectionResult>("/connectors/test", { method: "POST", body: JSON.stringify(body) }),
  testExistingConnection: (connectionId: string) =>
    request<TestConnectionResult>(`/connectors/${connectionId}/test`, { method: "POST" }),
  browseConnector: (body: {
    source_system: string;
    mode: "fixture" | "live";
    config: Record<string, unknown>;
    credential?: string;
  }) =>
    request<{ containers: BrowseContainer[] }>("/connectors/browse", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  browseExistingConnection: (connectionId: string) =>
    request<{ containers: BrowseContainer[] }>(`/connectors/${connectionId}/browse`, {
      method: "POST",
    }),
  updateConnectorConfig: (
    connectionId: string,
    config: Record<string, unknown>,
    displayName?: string
  ) =>
    request<ConnectorConnection>(`/connectors/${connectionId}`, {
      method: "PATCH",
      body: JSON.stringify({ config, display_name: displayName }),
    }),
  deleteConnector: (connectionId: string) =>
    request<void>(`/connectors/${connectionId}`, { method: "DELETE" }),
  triggerSync: (connectionId: string) =>
    request<SyncTriggerResult>(`/connectors/${connectionId}/sync`, { method: "POST" }),
  listSyncRuns: (connectionId: string) =>
    request<SyncRun[]>(`/connectors/${connectionId}/sync-runs`),
  listKinds: (sourceSystem?: string) => {
    const qs = sourceSystem ? `?source_system=${encodeURIComponent(sourceSystem)}` : "";
    return request<string[]>(`/catalog/kinds${qs}`);
  },
  searchCatalog: (params: {
    q?: string;
    source_system?: string;
    source_instance_id?: string;
    kind?: string;
    layer?: string;
  }) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][]
    ).toString();
    return request<CatalogNode[]>(`/catalog/search${qs ? `?${qs}` : ""}`);
  },
  getNode: (nodeId: string) => request<CatalogNode>(`/catalog/nodes/${nodeId}`),
  getNodeChildren: (nodeId: string) => request<CatalogNode[]>(`/catalog/nodes/${nodeId}/children`),
  getNodeDirectChildren: (nodeId: string) =>
    request<CatalogNode[]>(`/catalog/nodes/${nodeId}/direct-children`),
  getNodeAncestors: (nodeId: string) =>
    request<CatalogNode[]>(`/catalog/nodes/${nodeId}/ancestors`),
  getNodeLinks: (nodeId: string) => request<CatalogNodeLink[]>(`/catalog/nodes/${nodeId}/links`),
  createNodeLink: (nodeId: string, body: { target_node_id: string; type: string }) =>
    request<CatalogEdge>(`/catalog/nodes/${nodeId}/links`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteEdge: (edgeId: string) => request<void>(`/catalog/edges/${edgeId}`, { method: "DELETE" }),
  listProposedEdges: (type?: string) => {
    const qs = type ? `?type=${encodeURIComponent(type)}` : "";
    return request<ProposedEdge[]>(`/catalog/edges/proposed${qs}`);
  },
  confirmProposedEdge: (edgeId: string) =>
    request<CatalogEdge>(`/catalog/edges/${edgeId}/confirm`, { method: "POST" }),
  rejectProposedEdge: (edgeId: string) =>
    request<CatalogEdge>(`/catalog/edges/${edgeId}/reject`, { method: "POST" }),
  retypeProposedEdge: (edgeId: string, dstNodeId: string) =>
    request<CatalogEdge>(`/catalog/edges/${edgeId}/retype`, {
      method: "POST",
      body: JSON.stringify({ dst_node_id: dstNodeId }),
    }),
  getNodeGraph: (nodeId: string) => request<CatalogGraph>(`/catalog/nodes/${nodeId}/graph`),
  getEnterpriseGraph: () => request<CatalogGraph>("/catalog/enterprise-graph"),
  searchCards: (params: {
    q: string;
    business_node_id?: string;
    source_system?: string;
    limit?: number;
    semantic?: boolean;
  }) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [
        string,
        string,
      ][]
    ).toString();
    return request<SearchCard[]>(`/catalog/search-cards?${qs}`);
  },

  getOrgTree: () => request<BusinessNode[]>("/org/tree"),
  createBusinessNode: (body: {
    parent_id?: string | null;
    kind: string;
    name: string;
    description?: string;
    owners?: string[];
  }) => request<BusinessNode>("/org/nodes", { method: "POST", body: JSON.stringify(body) }),
  seedExampleOrgTree: () => request<BusinessNode[]>("/org/seed-example", { method: "POST" }),
  updateBusinessNode: (
    nodeId: string,
    body: {
      name?: string;
      description?: string;
      owners?: string[];
      criticality_tier?: string | null;
      compliance_scope?: string[] | null;
      stakeholders?: string[] | null;
      communication_channel?: CommunicationChannel | null;
    }
  ) => request<BusinessNode>(`/org/nodes/${nodeId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteBusinessNode: (nodeId: string) =>
    request<void>(`/org/nodes/${nodeId}`, { method: "DELETE" }),

  listContextSpaces: () => request<ContextSpace[]>("/context-spaces"),
  createContextSpace: (body: {
    id: string;
    name: string;
    description?: string;
    business_node_id: string;
    owners?: string[];
    product?: string | null;
    teams?: string[];
    services?: string[];
  }) => request<ContextSpace>("/context-spaces", { method: "POST", body: JSON.stringify(body) }),
  addContextSpaceBinding: (
    contextSpaceId: string,
    body: {
      capability: string;
      source_system: string;
      source_instance_id: string;
      native_container: string;
    }
  ) =>
    request<Binding>(`/context-spaces/${encodeURIComponent(contextSpaceId)}/bindings`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  removeContextSpaceBinding: (contextSpaceId: string, bindingId: string) =>
    request<void>(
      `/context-spaces/${encodeURIComponent(contextSpaceId)}/bindings/${bindingId}`,
      { method: "DELETE" }
    ),
  reconcileContextSpace: (contextSpaceId: string) =>
    request<ReconcileResult>(`/context-spaces/${encodeURIComponent(contextSpaceId)}/reconcile`),
  deleteContextSpace: (contextSpaceId: string) =>
    request<void>(`/context-spaces/${encodeURIComponent(contextSpaceId)}`, { method: "DELETE" }),
};
