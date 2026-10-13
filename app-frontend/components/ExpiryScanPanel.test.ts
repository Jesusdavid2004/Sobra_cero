import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  value: {
    t: {
      genericError: "Something went wrong",
      detailExpiryScans: "Expiry date suggestions",
      detailExpiryDisclaimer: "Review every suggested date before confirming it.",
      detailExpiryLoading: "Loading previous scans...",
      detailExpiryScan: "Read date from photo",
      detailExpiryScanning: "Reading photo...",
      detailExpiryNeedsImage: "Upload a lot photo before scanning.",
      detailExpiryActionError: "Could not complete this expiry-date action. Try again.",
      detailExpiryConfirmed: "The lot expiry date was updated.",
      detailExpiryRejected: "The suggested date was rejected.",
      detailExpiryAwaitingConfirmation: "Needs review",
      detailExpiryStatusConfirmed: "Confirmed",
      detailExpiryStatusRejected: "Rejected",
      detailExpiryUnreadable: "Unreadable",
      detailExpiryNoDate: "No readable date found",
      detailExpiryPrintedDate: "Text on package",
      detailExpiryConfidence: "Confidence: {percent}",
      detailExpiryConfirm: "Confirm date",
      detailExpiryReject: "Reject",
      detailExpiryNoScans: "No expiry-date scans yet.",
    },
    lang: "es",
    token: "access-token",
    authReady: true,
    user: { id: 11, email: "shop@example.com", role: "business", is_admin: false },
  },
  api: {
    shops: vi.fn(),
    expiryScans: vi.fn(),
    scanExpiryDate: vi.fn(),
    confirmExpiryScan: vi.fn(),
    rejectExpiryScan: vi.fn(),
  },
}));

vi.mock("@/providers/AppProviders", () => ({ useApp: () => state.value }));
vi.mock("@/lib/api", () => ({ api: state.api }));

import ExpiryScanPanel from "./ExpiryScanPanel";

const pendingSuggestion = {
  id: 3,
  printed_date: "Best before",
  expires_on: "2026-11-12",
  confidence: 0.94,
  status: "awaiting_confirmation" as const,
};

beforeEach(() => {
  vi.clearAllMocks();
  state.api.shops.mockResolvedValue([{ id: 5 }]);
  state.api.expiryScans.mockResolvedValue([]);
  state.api.scanExpiryDate.mockResolvedValue(pendingSuggestion);
  state.api.confirmExpiryScan.mockResolvedValue({
    ...pendingSuggestion,
    status: "confirmed",
  });
  state.api.rejectExpiryScan.mockResolvedValue({
    ...pendingSuggestion,
    status: "rejected",
  });
});

afterEach(() => cleanup());

describe("ExpiryScanPanel", () => {
  it("scans a lot image and applies the date only after confirmation", async () => {
    const onConfirmed = vi.fn();
    render(createElement(ExpiryScanPanel, { lotId: 9, shopId: 5, hasImage: true, onConfirmed }));

    fireEvent.click(await screen.findByRole("button", { name: "Read date from photo" }));
    expect(
      await screen.findByText(
        (_, element) =>
          element?.tagName === "P" && (element.textContent?.includes("Best before") ?? false),
      ),
    ).toBeInTheDocument();
    expect(state.api.scanExpiryDate).toHaveBeenCalledWith(9, "es");

    fireEvent.click(screen.getByRole("button", { name: "Confirm date" }));

    expect(await screen.findByText("Confirmed")).toBeInTheDocument();
    expect(onConfirmed).toHaveBeenCalledOnce();
  });

  it("does not offer confirmation for unreadable dates", async () => {
    state.api.expiryScans.mockResolvedValue([{ ...pendingSuggestion, status: "unreadable" }]);

    render(
      createElement(ExpiryScanPanel, { lotId: 9, shopId: 5, hasImage: true, onConfirmed: vi.fn() }),
    );

    expect(await screen.findByText("Unreadable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm date" })).not.toBeInTheDocument();
  });

  it("hides scan controls for a business that does not own the shop", async () => {
    state.api.shops.mockResolvedValue([{ id: 6 }]);

    render(
      createElement(ExpiryScanPanel, { lotId: 9, shopId: 5, hasImage: true, onConfirmed: vi.fn() }),
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Read date from photo" }),
      ).not.toBeInTheDocument(),
    );
    expect(state.api.expiryScans).not.toHaveBeenCalled();
  });

  it("requires an image before enabling scans", async () => {
    render(
      createElement(ExpiryScanPanel, {
        lotId: 9,
        shopId: 5,
        hasImage: false,
        onConfirmed: vi.fn(),
      }),
    );

    expect(await screen.findByRole("button", { name: "Read date from photo" })).toBeDisabled();
    expect(screen.getByText("Upload a lot photo before scanning.")).toBeInTheDocument();
  });
});
