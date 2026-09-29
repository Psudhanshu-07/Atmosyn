import { describe, expect, it } from "vitest";
import { pct, RISK_COLORS, riskLabel, VARIABLE_UNITS, VARIABLE_LABELS } from "./format";

describe("pct", () => {
  it("formats probabilities as percentages", () => {
    expect(pct(0.78)).toBe("78%");
    expect(pct(0.355, 1)).toBe("35.5%");
  });

  it("returns em dash for missing values", () => {
    expect(pct(null)).toBe("—");
    expect(pct(undefined)).toBe("—");
  });
});

describe("riskLabel", () => {
  it("humanises risk levels", () => {
    expect(riskLabel("VERY_HIGH")).toBe("VERY-HIGH");
    expect(riskLabel("LOW")).toBe("LOW");
    expect(riskLabel(undefined)).toBe("N/A");
  });

  it("keeps a colour per risk level (color-independent UI still needs labels)", () => {
    expect(Object.keys(RISK_COLORS)).toContain("VERY_HIGH");
    expect(Object.keys(RISK_COLORS)).toContain("NA");
  });
});

describe("meteorological constants and glossary", () => {
  it("has documented physical units for all core variables", () => {
    expect(VARIABLE_UNITS.rainfall).toBe("mm");
    expect(VARIABLE_UNITS.temperature).toBe("°C");
    expect(VARIABLE_UNITS.wind_speed).toBe("m/s");
    expect(VARIABLE_UNITS.pressure).toBe("hPa");
    expect(VARIABLE_UNITS.humidity).toBe("%");

    expect(VARIABLE_LABELS.rainfall).toBe("Rainfall");
  });
});
