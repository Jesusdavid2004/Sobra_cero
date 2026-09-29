export type User = { id: number; email: string; is_admin: boolean };
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
};
export type Shop = {
  id: number;
  owner_id: number;
  name: string;
  description: string;
  latitude: number;
  longitude: number;
};
export type Product = { id: number; shop_id: number; name: string; description: string };
export type Promotion = { id: number; language: string; variant: string; text: string; prompt: string };
export type Report = {
  users: number;
  shops: number;
  lots: number;
  reservations: number;
  donations: number;
};
export type Forecast = { shop_id: number; series: { day: number; predicted_lots: number }[] };

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${BASE}${path}`, { ...options, headers });
  if (response.status === 401) {
    window.localStorage.removeItem("token");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
    throw new Error(detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  shops: () => request<Shop[]>("/shops"),
  createShop: (data: Omit<Shop, "id" | "owner_id">) =>
    request<Shop>("/shops", { method: "POST", body: JSON.stringify(data) }),
  shopProducts: (shopId: number) => request<Product[]>(`/shops/${shopId}/products`),
  createProduct: (shopId: number, data: { name: string; description: string }) =>
    request<Product>(`/shops/${shopId}/products`, { method: "POST", body: JSON.stringify(data) }),
  lots: (params = "") => request<Lot[]>(`/lots${params}`),
  lot: (lotId: number) => request<Lot>(`/lots/${lotId}`),
  createLot: (data: unknown) => request<Lot>("/lots", { method: "POST", body: JSON.stringify(data) }),
  uploadImage: (lotId: number, file: Blob) => {
    const form = new FormData();
    form.append("image", file, "image.jpg");
    return request<Lot>(`/lots/${lotId}/image`, { method: "POST", body: form });
  },
  reserve: (lotId: number, quantity: number) =>
    request<{ id: number; status: string; quantity: number }>(`/lots/${lotId}/reserve`, {
      method: "POST",
      body: JSON.stringify({ quantity }),
    }),
  generatePromos: (lotId: number, lang: string) =>
    request<{ status: string }>(`/lots/${lotId}/generate-promos?language=${lang}`, { method: "POST" }),
  promos: (lotId: number) => request<Promotion[]>(`/lots/${lotId}/promos`),
  report: () => request<Report>("/admin/report"),
  forecast: (shopId: number) => request<Forecast>(`/shops/${shopId}/forecast`),
};