import { describe, expect, it } from "vitest";

import { nextThemePreference } from "./theme-preference";

describe("nextThemePreference", () => {
  it.each([
    ["system", "light"],
    ["light", "dark"],
    ["dark", "system"],
  ] as const)("cycles %s to %s", (current, expected) => {
    expect(nextThemePreference(current)).toBe(expected);
  });
});
