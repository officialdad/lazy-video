import { loadFont } from "@remotion/google-fonts/Anton";

// Anton: heavy condensed display face, the classic bold all-caps reel caption.
// Single weight (400) but visually very bold. Loaded once, reused everywhere.
const { fontFamily } = loadFont();

export const CAPTION_FONT = fontFamily;
