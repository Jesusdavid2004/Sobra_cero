import { afterEach, describe, expect, it, vi } from "vitest";

import { api, getToken, setAccessToken } from "@/lib/api";

const jsonResponse = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

describe("API session handling", () => {
  it("refreshes an expired access token and retries the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Unauthorized" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "new-access-token" }))
      .mockResolvedValueOnce(
        jsonResponse({ id: 1, email: "user@example.com", role: "customer", is_admin: false }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.me()).resolves.toMatchObject({ id: 1 });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: "POST",
      credentials: "include",
    });
    expect(fetchMock.mock.calls[2][1]?.credentials).toBe("include");
    expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get("Authorization")).toBe(
      "Bearer new-access-token",
    );
    expect(getToken()).toBe("new-access-token");
  });

  it("clears the in-memory access token after logout", async () => {
    setAccessToken("current-access-token");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchMock);

    await api.logout();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/auth/logout"),
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(getToken()).toBeNull();
  });
});
