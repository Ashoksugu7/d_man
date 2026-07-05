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
};

const PANT_CATS = new Set(["pant", "trouser", "trousers"]);

export function schemeFor(category: string, role?: string): Scheme {
  const c = (role || category || "").toLowerCase();
  if (PANT_CATS.has(c)) return SCHEMES.pant;
  if (c === "fullsleeve") return SCHEMES.fullsleeve;
  return SCHEMES.top; // shirt, tshirt, polo, ...
}

export const CATEGORIES = ["shirt", "tshirt", "fullsleeve", "pant"];

export function sizeChartFor(category: string): Record<string, any> {
  if (PANT_CATS.has(category))
    return { S: { waist_cm: 76, inseam_cm: 76 }, M: { waist_cm: 81, inseam_cm: 78 }, L: { waist_cm: 86, inseam_cm: 80 }, XL: { waist_cm: 91, inseam_cm: 81 } };
  return { S: { shoulder_cm: 42, length_cm: 68 }, M: { shoulder_cm: 45, length_cm: 71 }, L: { shoulder_cm: 48, length_cm: 74 }, XL: { shoulder_cm: 51, length_cm: 77 } };
}
