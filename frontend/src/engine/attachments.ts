import type { AttachmentDefinition, PrimitiveAttachment } from "../schemas/project";

const SVG_NS = "http://www.w3.org/2000/svg";
const SAFE_DATA_IMAGE = /^data:image\/png;base64,[a-z0-9+/=]+$/i;
const SAFE_URL = /^(#|https?:|data:image\/(?:png|jpeg|webp|gif);base64,)/i;

const DEFAULT_PRIMITIVES: Record<string, PrimitiveAttachment> = {
  capsule: { shape: "capsule", size: [0.48, 0.16], fill: "#e6b17a", opacity: 1 },
  ellipse: { shape: "ellipse", size: [0.42, 0.34], fill: "#f0c8a0", opacity: 1 },
  rectangle: { shape: "rectangle", size: [0.48, 0.28], fill: "#6b8fa8", opacity: 0.92 }
};

export function isSafePngDataUrl(value: string): boolean {
  return SAFE_DATA_IMAGE.test(value.trim());
}

function nextAttachmentId(boneId: string, existingIds: ReadonlySet<string>): string {
  const base = `part_${boneId.replace(/[^a-z0-9_]+/g, "_")}`;
  if (!existingIds.has(base)) {
    return base;
  }
  let index = 2;
  while (existingIds.has(`${base}_${index}`)) {
    index += 1;
  }
  return `${base}_${index}`;
}

export function createPrimitiveAttachment(options: {
  readonly boneId: string;
  readonly existingIds: ReadonlySet<string>;
  readonly shape?: PrimitiveAttachment["shape"];
}): AttachmentDefinition {
  const shape = options.shape ?? "capsule";
  return {
    id: nextAttachmentId(options.boneId, options.existingIds),
    bone_id: options.boneId,
    kind: "primitive",
    asset_id: null,
    primitive: DEFAULT_PRIMITIVES[shape],
    mesh: null,
    pivot: [0, 0],
    transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
    z_index: 0,
    visible: true
  };
}

export function updateAttachment(
  attachments: readonly AttachmentDefinition[],
  attachmentId: string,
  update: (attachment: AttachmentDefinition) => AttachmentDefinition
): AttachmentDefinition[] {
  let changed = false;
  const next = attachments.map((attachment) => {
    if (attachment.id !== attachmentId) {
      return attachment;
    }
    const updated = update(attachment);
    changed = changed || updated !== attachment;
    return updated;
  });
  return changed ? next : [...attachments];
}

export function sanitizeSvgMarkup(raw: string): string {
  const parser = new DOMParser();
  const document = parser.parseFromString(raw, "image/svg+xml");
  if (document.querySelector("parsererror") !== null) {
    throw new Error("SVG could not be parsed");
  }
  const svg = document.documentElement;
  if (svg.namespaceURI !== SVG_NS || svg.tagName.toLowerCase() !== "svg") {
    throw new Error("Imported SVG must have an <svg> root");
  }

  for (const element of Array.from(svg.querySelectorAll("*"))) {
    const tag = element.tagName.toLowerCase();
    if (["script", "foreignobject", "iframe", "object", "embed", "link"].includes(tag)) {
      element.remove();
      continue;
    }
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name.startsWith("on")) {
        element.removeAttribute(attribute.name);
      } else if ((name === "href" || name.endsWith(":href") || name === "src") && !SAFE_URL.test(value)) {
        element.removeAttribute(attribute.name);
      }
    }
  }

  for (const attribute of Array.from(svg.attributes)) {
    if (attribute.name.toLowerCase().startsWith("on")) {
      svg.removeAttribute(attribute.name);
    }
  }

  return new XMLSerializer().serializeToString(svg);
}
