// Keypoint schemes for the in-app annotator (mirrors tools/annotate.html).

export type Scheme = {
  order: string[];
  hints: Record<string, string>;
  guess: Record<string, [number, number]>; // fractions within alpha bbox
};

export const SCHEMES: Record<string, Scheme> = {
  top: {
    order: ["collar", "left_shoulder", "right_shoulder", "left_sleeve", "right_sleeve", "left_hem", "right_hem"],
    hints: {
      collar: "collar / neckline center",
      left_shoulder: "LEFT shoulder seam (image right)",
      right_shoulder: "RIGHT shoulder seam (image left)",
      left_sleeve: "left sleeve end",
      right_sleeve: "right sleeve end",
      left_hem: "bottom-left hem",
      right_hem: "bottom-right hem",
    },
    guess: { collar: [0.5, 0.04], left_shoulder: [0.25, 0.12], right_shoulder: [0.75, 0.12], left_sleeve: [0.04, 0.34], right_sleeve: [0.96, 0.34], left_hem: [0.27, 0.98], right_hem: [0.73, 0.98] },
  },
  fullsleeve: {
    order: ["collar", "left_shoulder", "right_shoulder", "left_sleeve", "right_sleeve", "left_hem", "right_hem"],
    hints: {
      collar: "collar / neckline center",
      left_shoulder: "LEFT shoulder seam (image right)",
      right_shoulder: "RIGHT shoulder seam (image left)",
      left_sleeve: "LEFT cuff (at the wrist)",
      right_sleeve: "RIGHT cuff (at the wrist)",
      left_hem: "bottom-left hem",
      right_hem: "bottom-right hem",
    },
    guess: { collar: [0.5, 0.04], left_shoulder: [0.26, 0.12], right_shoulder: [0.74, 0.12], left_sleeve: [0.05, 0.66], right_sleeve: [0.95, 0.66], left_hem: [0.3, 0.98], right_hem: [0.7, 0.98] },
  },
  pant: {
    order: ["left_waist", "right_waist", "crotch", "left_ankle", "right_ankle"],
    hints: {
      left_waist: "LEFT waistband corner (image right)",
      right_waist: "RIGHT waistband corner (image left)",
      crotch: "crotch (center)",
      left_ankle: "left leg ankle hem",
      right_ankle: "right leg ankle hem",
    },
    guess: { left_waist: [0.18, 0.03], right_waist: [0.82, 0.03], crotch: [0.5, 0.52], left_ankle: [0.3, 0.98], right_ankle: [0.7, 0.98] },
  },
  skirt: {
    order: ["left_waist", "right_waist", "left_hem", "right_hem"],
    hints: {
      left_waist: "LEFT waistband corner (image right)",
      right_waist: "RIGHT waistband corner (image left)",
      left_hem: "bottom-left hem (flared)",
      right_hem: "bottom-right hem (flared)",
    },
    guess: { left_waist: [0.35, 0.04], right_waist: [0.65, 0.04], left_hem: [0.04, 0.98], right_hem: [0.96, 0.98] },
  },
  dupatta: {
    order: ["left_shoulder", "right_shoulder", "left_hem", "right_hem"],
    hints: {
      left_shoulder: "LEFT shoulder anchor (image right)",
      right_shoulder: "RIGHT shoulder anchor (image left)",
      left_hem: "bottom-left of the drape",
      right_hem: "bottom-right of the drape",
    },
    guess: { left_shoulder: [0.08, 0.06], right_shoulder: [0.92, 0.06], left_hem: [0.2, 0.96], right_hem: [0.8, 0.96] },
  },
  pallu: {
    order: ["top_left", "top_right", "left_hem", "right_hem"],
    hints: {
      top_left: "top-left of sash (over shoulder)",
      top_right: "top-right of sash",
      left_hem: "bottom-left of hanging end",
      right_hem: "bottom-right of hanging end",
    },
    guess: { top_left: [0.14, 0.06], top_right: [0.57, 0.06], left_hem: [0.43, 0.96], right_hem: [0.86, 0.96] },
  },
};

const PANT_CATS = new Set(["pant", "salwar", "palazzo", "trouser", "trousers"]);
const SKIRT_CATS = new Set(["skirt"]);

export function schemeFor(category: string, role?: string): Scheme {
  const c = (role || category || "").toLowerCase();
  if (PANT_CATS.has(c)) return SCHEMES.pant;
  if (SKIRT_CATS.has(c)) return SCHEMES.skirt;
  if (c === "dupatta") return SCHEMES.dupatta;
  if (c === "pallu") return SCHEMES.pallu;
  if (c === "fullsleeve") return SCHEMES.fullsleeve;
  return SCHEMES.top; // shirt, tshirt, polo, kurta, blouse, ...
}

export const CATEGORIES = [
  "shirt", "tshirt", "fullsleeve", "polo", "kurta", "dupatta", "blouse",
  "pant", "salwar", "palazzo", "skirt", "lehenga", "saree",
];

export function sizeChartFor(category: string): Record<string, any> {
  if (PANT_CATS.has(category))
    return { S: { waist_cm: 76, inseam_cm: 76 }, M: { waist_cm: 81, inseam_cm: 78 }, L: { waist_cm: 86, inseam_cm: 80 }, XL: { waist_cm: 91, inseam_cm: 81 } };
  if (SKIRT_CATS.has(category) || category === "lehenga")
    return { S: { waist_cm: 66 }, M: { waist_cm: 71 }, L: { waist_cm: 76 }, XL: { waist_cm: 81 } };
  if (category === "dupatta" || category === "saree")
    return { M: { length_cm: 230, width_cm: 90 } };
  if (category === "kurta")
    return { S: { shoulder_cm: 42, length_cm: 100 }, M: { shoulder_cm: 45, length_cm: 104 }, L: { shoulder_cm: 48, length_cm: 108 }, XL: { shoulder_cm: 51, length_cm: 112 } };
  return { S: { shoulder_cm: 42, length_cm: 68 }, M: { shoulder_cm: 45, length_cm: 71 }, L: { shoulder_cm: 48, length_cm: 74 }, XL: { shoulder_cm: 51, length_cm: 77 } };
}
