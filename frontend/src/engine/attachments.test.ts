import { describe, expect, it } from "vitest";

import {
  createPrimitiveAttachment,
  isSafePngDataUrl,
  sanitizeSvgMarkup,
  updateAttachment
} from "./attachments";

describe("attachment helpers", () => {
  it("creates stable primitive attachment ids without collisions", () => {
    const first = createPrimitiveAttachment({
      boneId: "forearm_r",
      existingIds: new Set(),
      shape: "capsule"
    });
    const second = createPrimitiveAttachment({
      boneId: "forearm_r",
      existingIds: new Set([first.id]),
      shape: "ellipse"
    });

    expect(first.id).toBe("part_forearm_r");
    expect(second.id).toBe("part_forearm_r_2");
    expect(second.primitive?.shape).toBe("ellipse");
  });

  it("updates attachments immutably", () => {
    const attachment = createPrimitiveAttachment({
      boneId: "head",
      existingIds: new Set(),
      shape: "ellipse"
    });
    const updated = updateAttachment([attachment], attachment.id, (current) => ({
      ...current,
      visible: false
    }));

    expect(updated).not.toBe([attachment]);
    expect(updated[0]).toEqual({ ...attachment, visible: false });
    expect(attachment.visible).toBe(true);
  });

  it("sanitizes executable SVG content and unsafe links", () => {
    const sanitized = sanitizeSvgMarkup(`
      <svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">
        <script>alert(1)</script>
        <rect onclick="alert(2)" href="javascript:alert(3)" width="10" height="10" />
      </svg>
    `);

    expect(sanitized).not.toContain("script");
    expect(sanitized).not.toContain("onload");
    expect(sanitized).not.toContain("onclick");
    expect(sanitized).not.toContain("javascript:");
    expect(sanitized).toContain("<rect");
  });

  it("accepts only PNG data URLs for image imports", () => {
    expect(isSafePngDataUrl("data:image/png;base64,abcdABCD0123+/=")).toBe(true);
    expect(isSafePngDataUrl("data:image/svg+xml;base64,abcd")).toBe(false);
    expect(isSafePngDataUrl("https://example.test/image.png")).toBe(false);
  });
});
