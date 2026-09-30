import { describe, it, expect } from "vitest";
import { api } from "../lib/api";

describe("api query serialization", () => {
  it("serializes array params as repeated keys for FastAPI", () => {
    const uri = api.getUri({
      url: "/work-orders",
      params: { status_id: [3, 7], page: 1 },
    });
    expect(uri).toContain("status_id=3&status_id=7");
    expect(uri).not.toContain("status_id[]");
  });
});
