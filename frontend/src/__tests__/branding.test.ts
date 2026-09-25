import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const loginSource = readFileSync(
  resolve(process.cwd(), "src/views/LoginView.vue"),
  "utf8",
);
const dashboardSource = readFileSync(
  resolve(process.cwd(), "src/views/DashboardView.vue"),
  "utf8",
);
const globalStyles = readFileSync(
  resolve(process.cwd(), "src/styles/global.css"),
  "utf8",
);
const brandingAsset = readFileSync(
  resolve(process.cwd(), "public/branding/vogel-servicios-workshop-bg.webp"),
);

describe("Vogel workshop branding", () => {
  it("uses the approved asset for the login and dashboard hero", () => {
    expect(loginSource).toContain("auth-shell__hero--branding");
    expect(dashboardSource).toContain("hero--branding");
    expect(globalStyles).toContain(
      "/branding/vogel-servicios-workshop-bg.webp",
    );
    expect(loginSource).not.toContain("images.unsplash.com");
    expect(dashboardSource).not.toContain("images.unsplash.com");
  });

  it("ships a non-empty branding asset", () => {
    expect(brandingAsset.byteLength).toBeGreaterThan(0);
  });
});
