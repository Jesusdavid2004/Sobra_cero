import { z } from "zod";

const ExpiryScanSuggestionSchema = z.object({
  id: z.number().int(),
  printed_date: z.string().max(80).nullable(),
  expires_on: z.iso.date().nullable(),
  confidence: z.number().min(0).max(1),
  status: z.enum(["awaiting_confirmation", "confirmed", "rejected", "unreadable"]),
});

export type ExpiryScanSuggestion = z.infer<typeof ExpiryScanSuggestionSchema>;

export type User = {
  id: number;
  email: string;
  role: "business" | "customer";
  is_admin: boolean;
};
export type Lot = {
  id: number;
  shop_id: number;
  product_id: number;
  title: string;
  description: string;
  quantity: number;
  original_price_cents: number;
  discount_percent: number;
  expires_at: string;
  image_url?: string | null;
  category: string;
  business_type: "restaurant" | "supermarket";
};
export type Shop = {
  id: number;
  owner_id: number;
  name: string;
  business_type: "restaurant" | "supermarket";
  description: string;
  latitude: number;
  longitude: number;
};
export type Product = {
  id: number;
  shop_id: number;
  name: string;
  description: string;
  category: string;
};
export type Promotion = {
  id: number;
  language: string;
  variant: string;
  text: string;
  prompt: string;
};
export type Report = {
  users: number;
  shops: number;
  lots: number;
  reservations: number;
  donations: number;
};
export type Forecast = { shop_id: number; series: { day: number; predicted_lots: number }[] };
export type WasteRisk = {
  product_id: number;
  product_name: string;
  lot_id: number;
  current_stock: number;
  days_remaining: number;
  data_points: number;
  average_daily_sales: number;
  expected_sales: number;
  units_at_risk: number;
  risk_score: number;
  risk_level: "low" | "medium" | "high";
  recommendation: string;
  prediction_model: string;
  calculated_at: string;
};
export type SalesHistoryCreated = { created: number; existing: number };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;
const accessTokenListeners = new Set<(token: string | null) => void>();

export function getToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
  for (const listener of accessTokenListeners) listener(token);
}

export function subscribeToAccessToken(listener: (token: string | null) => void): () => void {
  accessTokenListeners.add(listener);
  return () => accessTokenListeners.delete(listener);
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then(async (response) => {
        if (response.status === 401) {
          setAccessToken(null);
          return null;
        }
        if (!response.ok) {
          throw new ApiError(`Request failed (${response.status})`, response.status);
        }
        const body = (await response.json()) as { access_token: string };
        setAccessToken(body.access_token);
        return body.access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  allowRefresh = true,
): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (typeof document !== "undefined") {
    headers.set("Accept-Language", document.documentElement.lang || "en");
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  const isSessionEndpoint = [
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/auth/logout",
  ].includes(path);
  if (response.status === 401 && allowRefresh && !isSessionEndpoint) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) return request<T>(path, options, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
    throw new ApiError(detail ?? `Request failed (${response.status})`, response.status, body.code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, role: User["role"] = "business") =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, role }),
    }),
  refresh: () => refreshAccessToken(),
  logout: async () => {
    await request<void>("/auth/logout", { method: "POST" }, false);
    setAccessToken(null);
  },
  me: () => request<User>("/auth/me"),
  shops: () => request<Shop[]>("/shops"),
  createShop: (data: Omit<Shop, "id" | "owner_id">) =>
    request<Shop>("/shops", { method: "POST", body: JSON.stringify(data) }),
  shopProducts: (shopId: number) => request<Product[]>(`/shops/${shopId}/products`),
  createProduct: (shopId: number, data: { name: string; description: string; category: string }) =>
    request<Product>(`/shops/${shopId}/products`, { method: "POST", body: JSON.stringify(data) }),
  lots: (filters: { category?: string; business_type?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.category) params.set("category", filters.category);
    if (filters.business_type) params.set("business_type", filters.business_type);
    const query = params.toString();
    return request<Lot[]>(`/lots${query ? `?${query}` : ""}`);
  },
  lot: (lotId: number) => request<Lot>(`/lots/${lotId}`),
  createLot: (data: unknown) =>
    request<Lot>("/lots", { method: "POST", body: JSON.stringify(data) }),
  uploadImage: (lotId: number, file: Blob) => {
    const form = new FormData();
    form.append("image", file, "image.jpg");
    return request<Lot>(`/lots/${lotId}/image`, { method: "POST", body: form });
  },
  reserve: (lotId: number, quantity: number) =>
    request<{ id: number; status: string; quantity: number; pickup_code: string }>(
      `/lots/${lotId}/reserve`,
      {
        method: "POST",
        body: JSON.stringify({ quantity }),
      },
    ),
  generatePromos: (lotId: number, lang: string) =>
    request<{ status: string }>(`/lots/${lotId}/generate-promos?language=${lang}`, {
      method: "POST",
    }),
  promos: (lotId: number) => request<Promotion[]>(`/lots/${lotId}/promos`),
  report: () => request<Report>("/admin/report"),
  forecast: (shopId: number) => request<Forecast>(`/shops/${shopId}/forecast`),
  wasteRisk: (shopId: number, language: string) =>
    request<WasteRisk[]>(`/shops/${shopId}/waste-risk?language=${language}`),
  loadSampleSalesHistory: (shopId: number) =>
    request<SalesHistoryCreated>(`/shops/${shopId}/sales-history/sample`, { method: "POST" }),
  expiryScans: async (lotId: number) =>
    ExpiryScanSuggestionSchema.array().parse(await request<unknown>(`/lots/${lotId}/expiry-scans`)),
  scanExpiryDate: async (lotId: number, language: string) => {
    const params = new URLSearchParams({ language });
    return ExpiryScanSuggestionSchema.parse(
      await request<unknown>(`/lots/${lotId}/expiry-scans?${params}`, { method: "POST" }),
    );
  },
  confirmExpiryScan: async (lotId: number, suggestionId: number) =>
    ExpiryScanSuggestionSchema.parse(
      await request<unknown>(`/lots/${lotId}/expiry-scans/${suggestionId}/confirm`, {
        method: "POST",
      }),
    ),
  rejectExpiryScan: async (lotId: number, suggestionId: number) =>
    ExpiryScanSuggestionSchema.parse(
      await request<unknown>(`/lots/${lotId}/expiry-scans/${suggestionId}/reject`, {
        method: "POST",
      }),
    ),
};
