// scripts/contrast.mjs
// Checks text/background and UI border token pairs against WCAG AA requirements
// 4.5:1 for normal body text, 3:1 for large text and UI borders.

function hexToRgb(hex) {
  const cleanHex = hex.replace('#', '');
  const bigint = parseInt(cleanHex, 16);
  return {
    r: (bigint >> 16) & 255,
    g: (bigint >> 8) & 255,
    b: bigint & 255,
  };
}

function getLuminance({ r, g, b }) {
  const [rs, gs, bs] = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

function getContrastRatio(hex1, hex2) {
  const lum1 = getLuminance(hexToRgb(hex1));
  const lum2 = getLuminance(hexToRgb(hex2));
  const brightest = Math.max(lum1, lum2);
  const darkest = Math.min(lum1, lum2);
  return (brightest + 0.05) / (darkest + 0.05);
}

// Token palette definitions
const tokens = {
  paper: '#F5F6F4',
  surface: '#FFFFFF',
  ink: '#16202A',
  'ink-2': '#4A5663',
  'ink-3': '#667381',
  line: '#DDE2E7',
  'line-strong': '#7E8E9E', // Adjusted from #C3CBD3 to satisfy WCAG 1.4.11 UI border contrast (>= 3.0:1)
  brand: '#0F5C4D',
  'brand-wash': '#E4F0EC',
  turmeric: '#B37400', // Adjusted from #D99A1B to achieve >= 3:1 UI border & large text contrast
  'turmeric-wash': '#FBF0D7',
  madder: '#A3344F',
  'madder-wash': '#F7E4E9',
  ok: '#2E7D4F',
};

// Defined token usage pairs in the design system
const testPairs = [
  // Primary text pairs (Target >= 4.5:1)
  { type: 'text', name: 'ink on surface', fg: tokens.ink, bg: tokens.surface, target: 4.5 },
  { type: 'text', name: 'ink on paper', fg: tokens.ink, bg: tokens.paper, target: 4.5 },
  { type: 'text', name: 'ink-2 on surface', fg: tokens['ink-2'], bg: tokens.surface, target: 4.5 },
  { type: 'text', name: 'ink-2 on paper', fg: tokens['ink-2'], bg: tokens.paper, target: 4.5 },
  { type: 'text', name: 'ink-3 on surface (smallest meta)', fg: tokens['ink-3'], bg: tokens.surface, target: 4.5 },
  { type: 'text', name: 'brand on surface', fg: tokens.brand, bg: tokens.surface, target: 4.5 },
  { type: 'text', name: 'brand on brand-wash', fg: tokens.brand, bg: tokens['brand-wash'], target: 4.5 },
  { type: 'text', name: 'surface (white) on brand', fg: tokens.surface, bg: tokens.brand, target: 4.5 },
  { type: 'text', name: 'madder on surface', fg: tokens.madder, bg: tokens.surface, target: 4.5 },
  { type: 'text', name: 'madder on madder-wash', fg: tokens.madder, bg: tokens['madder-wash'], target: 4.5 },
  { type: 'text', name: 'ok on surface', fg: tokens.ok, bg: tokens.surface, target: 4.5 },
  { type: 'text', name: 'ink on turmeric-wash', fg: tokens.ink, bg: tokens['turmeric-wash'], target: 4.5 },

  // Large text & UI borders (Target >= 3.0:1)
  { type: 'border', name: 'line-strong border on surface', fg: tokens['line-strong'], bg: tokens.surface, target: 3.0 },
  { type: 'border', name: 'line-strong border on paper', fg: tokens['line-strong'], bg: tokens.paper, target: 3.0 },
  { type: 'border', name: 'turmeric stamp border on surface', fg: tokens.turmeric, bg: tokens.surface, target: 3.0 },
  { type: 'border', name: 'turmeric stamp border on paper', fg: tokens.turmeric, bg: tokens.paper, target: 3.0 },
  { type: 'border', name: 'brand focus ring on surface', fg: tokens.brand, bg: tokens.surface, target: 3.0 },
  { type: 'border', name: 'brand focus ring on paper', fg: tokens.brand, bg: tokens.paper, target: 3.0 },
  { type: 'border', name: 'madder indicator rule on surface', fg: tokens.madder, bg: tokens.surface, target: 3.0 },
  { type: 'border', name: 'madder indicator rule on paper', fg: tokens.madder, bg: tokens.paper, target: 3.0 },
];

let failed = 0;
console.log('--- Checking Design System Contrast Ratios (WCAG AA) ---');

for (const pair of testPairs) {
  const ratio = getContrastRatio(pair.fg, pair.bg);
  const ratioStr = ratio.toFixed(2) + ':1';
  const passed = ratio >= pair.target;

  if (passed) {
    console.log(`PASS: [${pair.type.toUpperCase()}] ${pair.name} -> ${ratioStr} (min ${pair.target}:1)`);
  } else {
    console.error(`FAIL: [${pair.type.toUpperCase()}] ${pair.name} -> ${ratioStr} (FAILED: requires ${pair.target}:1)`);
    failed++;
  }
}

console.log('---------------------------------------------------------');
if (failed > 0) {
  console.error(`ERROR: ${failed} contrast check(s) failed. Build aborted.`);
  process.exit(1);
} else {
  console.log(`SUCCESS: All ${testPairs.length} contrast checks passed.`);
}
