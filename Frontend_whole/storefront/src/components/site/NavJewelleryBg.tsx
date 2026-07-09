export function NavJewelleryBg() {
  // Pearl string positions — gentle sine wave from x=880 to x=1432
  const pearls = Array.from({ length: 22 }, (_, i) => ({
    x: 880 + i * 26,
    y: 94 + Math.sin(i * 0.9) * 3.5,
  }));

  // Necklace chain link cx values; cy increases as the arc descends
  const chainLinks = [30, 70, 110, 150, 190, 230, 270, 310, 350, 390, 430];

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 1440 110"
      preserveAspectRatio="xMinYMid slice"
      xmlns="http://www.w3.org/2000/svg"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
    >
      <style>{`
        .njb {
          stroke: var(--primary);
          animation: njbFloat 9s ease-in-out infinite;
        }
        @keyframes njbFloat {
          0%,100% { transform: translateY(0px);    opacity: 0.25; }
          50%      { transform: translateY(-2.5px); opacity: 0.32; }
        }
        @media (prefers-reduced-motion: reduce) {
          .njb { animation: none; opacity: 0.28; }
        }
        /* Tablet (≥768px): show mid-density elements */
        .njb-md  { display: none; }
        @media (min-width: 768px)  { .njb-md { display: block; } }
        /* Desktop (≥1024px): show full illustration */
        .njb-lg  { display: none; }
        @media (min-width: 1024px) { .njb-lg { display: block; } }
      `}</style>

      <g
        className="njb"
        fill="none"
        strokeWidth="0.72"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* ── NECKLACE CHAIN — enters from left, flows across top ──────── */}
        <g className="njb-md">
          <path d="M-15,22 C50,20 120,24 200,30 C280,36 355,42 435,46 C495,49 535,46 565,42" />
          {/* Oval chain links placed along the arc */}
          {chainLinks.map((cx, i) => {
            const cy = 22 + i * 2.4;
            const angle = -5 + i * 1.1;
            return (
              <ellipse
                key={cx}
                cx={cx}
                cy={cy}
                rx="8"
                ry="3"
                transform={`rotate(${angle},${cx},${cy})`}
              />
            );
          })}
        </g>

        {/* ── STUD EARRING — far left ───────────────────────────────────── */}
        {/* md+ only: at mobile widths the header's shorter box (utility bar
            collapses to 0 height) rescales this coordinate space enough that
            an unmasked element out here reads as a random floating circle
            near the menu button instead of a background accent. */}
        <g transform="translate(58,34)" className="njb-md">
          <circle r="9" />
          <circle r="4" />
          {Array.from({ length: 6 }).map((_, i) => {
            const a = (i * 60 * Math.PI) / 180;
            return (
              <line
                key={i}
                x1={Math.cos(a) * 4}
                y1={Math.sin(a) * 4}
                x2={Math.cos(a) * 9}
                y2={Math.sin(a) * 9}
              />
            );
          })}
        </g>

        {/* ── DIAMOND SOLITAIRE — round brilliant, sits behind logo ────── */}
        {/* Always visible so mobile gets at least one jewellery element */}
        <g transform="translate(165,62)">
          {/* Girdle */}
          <circle r="20" />
          {/* Table */}
          <circle r="10" />
          {/* 8 radial facet lines: table edge → girdle */}
          {Array.from({ length: 8 }).map((_, i) => {
            const a = (i * 45 * Math.PI) / 180;
            return (
              <line
                key={i}
                x1={Math.cos(a) * 10}
                y1={Math.sin(a) * 10}
                x2={Math.cos(a) * 20}
                y2={Math.sin(a) * 20}
              />
            );
          })}
        </g>

        {/* ── PENDANT — hangs from necklace ────────────────────────────── */}
        <g transform="translate(455,44)" className="njb-md">
          {/* Bail loop */}
          <ellipse cx="0" cy="3" rx="5" ry="4" />
          <line x1="0" y1="7" x2="0" y2="14" />
          {/* Pear-shaped pendant */}
          <path d="M-11,18 C-11,10 -6,8 0,8 C6,8 11,10 11,18 Q11,34 0,40 Q-11,34 -11,18 Z" />
          {/* Inner light reflection */}
          <path d="M-4,18 Q-2,30 0,36" />
        </g>

        {/* ── SPARKLE — left zone (also visible on mobile) ─────────────── */}
        <g transform="translate(320,78)">
          <line x1="0" y1="-6" x2="0" y2="6" />
          <line x1="-6" y1="0" x2="6" y2="0" />
          <line x1="-3" y1="-3" x2="3" y2="3" />
          <line x1="3" y1="-3" x2="-3" y2="3" />
        </g>

        {/* ── FLOURISH — small flanking curves, fills the gap before the
             pendant so tablet-width views (where the illustration's right
             half gets cropped by the `slice` scaling) aren't left sparse ── */}
        <g transform="translate(248,42)" className="njb-md">
          <path d="M-12,4 C-4,-4 4,-4 12,4" />
          <path d="M-9,10 C-3,6 3,6 9,10" />
        </g>

        {/* ── BANGLE — small nested-circle band, before the pendant ────── */}
        <g transform="translate(398,66)" className="njb-md">
          <circle r="13" />
          <circle r="8.5" />
        </g>

        {/* ── SPARKLE — small accent right at the tablet crop edge ─────── */}
        <g transform="translate(608,58)" className="njb-md">
          <line x1="0" y1="-4" x2="0" y2="4" />
          <line x1="-4" y1="0" x2="4" y2="0" />
        </g>

        {/* ── MARQUISE CUT GEM — centre-left ───────────────────────────── */}
        <g transform="translate(580,30)" className="njb-lg">
          <path d="M-18,0 Q0,-11 18,0 Q0,11 -18,0 Z" />
          <line x1="-18" y1="0" x2="18" y2="0" />
          <line x1="0" y1="-11" x2="0" y2="11" />
          <path d="M-9,-7 Q0,-11 9,-7" />
          <path d="M-9,7 Q0,11 9,7" />
        </g>

        {/* ── EARRING DROP — just off-centre ───────────────────────────── */}
        <g transform="translate(755,2)" className="njb-lg">
          {/* Shepherd's hook */}
          <path d="M0,5 C-4,4 -6,9 -4,13 C-2,17 0,18 0,18" />
          {/* Drop wire */}
          <line x1="0" y1="18" x2="0" y2="38" />
          {/* Pear drop gemstone */}
          <path d="M-7,42 C-7,38 -3,36 0,36 C3,36 7,38 7,42 Q7,56 0,62 Q-7,56 -7,42 Z" />
        </g>

        {/* ── SPARKLE — centre ─────────────────────────────────────────── */}
        <g transform="translate(650,88)" className="njb-md">
          <line x1="0" y1="-5" x2="0" y2="5" />
          <line x1="-5" y1="0" x2="5" y2="0" />
          <line x1="-2.5" y1="-2.5" x2="2.5" y2="2.5" />
          <line x1="2.5" y1="-2.5" x2="-2.5" y2="2.5" />
        </g>

        {/* ── RING — side view, right-centre ───────────────────────────── */}
        <g transform="translate(950,68)" className="njb-lg">
          {/* Band top oval */}
          <ellipse rx="20" ry="8" />
          {/* Shank sides */}
          <line x1="-20" y1="0" x2="-20" y2="22" />
          <line x1="20" y1="0" x2="20" y2="22" />
          {/* Shank bottom arc */}
          <path d="M-20,22 Q0,32 20,22" />
          {/* Solitaire stone set atop band */}
          <ellipse cy="-8" rx="8" ry="6" />
          <line x1="-8" y1="-8" x2="8" y2="-8" />
          <line x1="0" y1="-14" x2="0" y2="-2" />
        </g>

        {/* ── ORNAMENTAL CURVES — fine flourish ────────────────────────── */}
        <g className="njb-lg">
          <path d="M855,10 C865,7 875,10 885,7 C895,4 905,7 915,10" />
          <path d="M855,10 C860,15 855,20 862,26" />
          <path d="M915,10 C910,15 915,20 908,26" />
        </g>

        {/* ── SPARKLE — right area ─────────────────────────────────────── */}
        <g transform="translate(1080,22)" className="njb-lg">
          <line x1="0" y1="-7" x2="0" y2="7" />
          <line x1="-7" y1="0" x2="7" y2="0" />
          <line x1="-3.5" y1="-3.5" x2="3.5" y2="3.5" />
          <line x1="3.5" y1="-3.5" x2="-3.5" y2="3.5" />
        </g>

        {/* ── BRACELET CHAIN — right side, exits frame ─────────────────── */}
        <g className="njb-lg">
          <path d="M1165,42 C1200,37 1240,47 1280,41 C1315,36 1362,46 1440,40" />
          {/* Oval bracelet links */}
          {[1175, 1205, 1235, 1265, 1295, 1325, 1362].map((cx, i) => {
            const cy = 42 + (i % 2 === 0 ? -1 : 1) * 2;
            const angle = i % 2 === 0 ? -6 : 4;
            return (
              <ellipse
                key={cx}
                cx={cx}
                cy={cy}
                rx="9"
                ry="3.5"
                transform={`rotate(${angle},${cx},${cy})`}
              />
            );
          })}
        </g>

        {/* ── PEARL STRING — right half, bottom of navbar ──────────────── */}
        <g className="njb-lg">
          {/* Connecting thread */}
          <path d="M880,94 Q960,90 1040,96 Q1120,101 1200,93 Q1300,86 1380,92 Q1415,95 1440,93" />
          {pearls.map(({ x, y }, i) => (
            <circle key={i} cx={x} cy={y} r="3.5" />
          ))}
        </g>

        {/* ── SPARKLE — far right ───────────────────────────────────────── */}
        <g transform="translate(1388,70)" className="njb-lg">
          <line x1="0" y1="-5" x2="0" y2="5" />
          <line x1="-5" y1="0" x2="5" y2="0" />
          <line x1="-2.5" y1="-2.5" x2="2.5" y2="2.5" />
          <line x1="2.5" y1="-2.5" x2="-2.5" y2="2.5" />
        </g>
      </g>
    </svg>
  );
}
