export function NavJewelleryBgMobile() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 340 800"
      preserveAspectRatio="xMidYMid slice"
      xmlns="http://www.w3.org/2000/svg"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
    >
      <style>{`
        .njbm {
          stroke: var(--primary);
          animation: njbmFloat 9s ease-in-out infinite;
        }
        @keyframes njbmFloat {
          0%,100% { transform: translateY(0px);    opacity: 0.18; }
          50%      { transform: translateY(-2.5px); opacity: 0.25; }
        }
        @media (prefers-reduced-motion: reduce) {
          .njbm { animation: none; opacity: 0.2; }
        }
      `}</style>

      <g className="njbm" fill="none" strokeWidth="0.72" strokeLinecap="round" strokeLinejoin="round">

        {/* ── Necklace chain — flows down from top-right ── */}
        <path d="M200,10 C230,20 260,35 280,60 C300,85 300,120 280,145" />
        {[
          [205, 14], [220, 22], [240, 34], [258, 48], [272, 66],
          [284, 88], [287, 112], [281, 136],
        ].map(([cx, cy], i) => (
          <ellipse key={i} cx={cx} cy={cy} rx="7" ry="2.5" transform={`rotate(${-60 + i * 10},${cx},${cy})`} />
        ))}

        {/* ── Pendant — hangs from chain ── */}
        <g transform="translate(278,148)">
          <ellipse cx="0" cy="3" rx="4" ry="3" />
          <line x1="0" y1="6" x2="0" y2="14" />
          <path d="M-10,18 C-10,11 -5,9 0,9 C5,9 10,11 10,18 Q10,30 0,36 Q-10,30 -10,18 Z" />
          <path d="M-3,18 Q-1,28 0,33" />
        </g>

        {/* ── Diamond solitaire — upper left ── */}
        <g transform="translate(55,80)">
          <circle r="22" />
          <circle r="11" />
          {Array.from({ length: 8 }).map((_, i) => {
            const a = (i * 45 * Math.PI) / 180;
            return (
              <line
                key={i}
                x1={Math.cos(a) * 11} y1={Math.sin(a) * 11}
                x2={Math.cos(a) * 22} y2={Math.sin(a) * 22}
              />
            );
          })}
        </g>

        {/* ── Sparkle — top left ── */}
        <g transform="translate(30,30)">
          <line x1="0" y1="-7" x2="0" y2="7" />
          <line x1="-7" y1="0" x2="7" y2="0" />
          <line x1="-3.5" y1="-3.5" x2="3.5" y2="3.5" />
          <line x1="3.5" y1="-3.5" x2="-3.5" y2="3.5" />
        </g>

        {/* ── Sparkle — mid right ── */}
        <g transform="translate(310,260)">
          <line x1="0" y1="-5" x2="0" y2="5" />
          <line x1="-5" y1="0" x2="5" y2="0" />
          <line x1="-2.5" y1="-2.5" x2="2.5" y2="2.5" />
          <line x1="2.5" y1="-2.5" x2="-2.5" y2="2.5" />
        </g>

        {/* ── Ring — mid left ── */}
        <g transform="translate(50,280)">
          <ellipse rx="22" ry="9" />
          <line x1="-22" y1="0" x2="-22" y2="24" />
          <line x1="22" y1="0" x2="22" y2="24" />
          <path d="M-22,24 Q0,36 22,24" />
          <ellipse cy="-9" rx="9" ry="6" />
          <line x1="-9" y1="-9" x2="9" y2="-9" />
          <line x1="0" y1="-15" x2="0" y2="-3" />
        </g>

        {/* ── Marquise gem — centre ── */}
        <g transform="translate(185,380)">
          <path d="M-20,0 Q0,-12 20,0 Q0,12 -20,0 Z" />
          <line x1="-20" y1="0" x2="20" y2="0" />
          <line x1="0" y1="-12" x2="0" y2="12" />
          <path d="M-10,-8 Q0,-12 10,-8" />
          <path d="M-10,8 Q0,12 10,8" />
        </g>

        {/* ── Sparkle — centre left ── */}
        <g transform="translate(28,420)">
          <line x1="0" y1="-6" x2="0" y2="6" />
          <line x1="-6" y1="0" x2="6" y2="0" />
          <line x1="-3" y1="-3" x2="3" y2="3" />
          <line x1="3" y1="-3" x2="-3" y2="3" />
        </g>

        {/* ── Earring drop — right side ── */}
        <g transform="translate(300,460)">
          <path d="M0,5 C-4,4 -6,9 -4,13 C-2,17 0,18 0,18" />
          <line x1="0" y1="18" x2="0" y2="40" />
          <path d="M-7,44 C-7,39 -3,37 0,37 C3,37 7,39 7,44 Q7,58 0,64 Q-7,58 -7,44 Z" />
        </g>

        {/* ── Ornamental curves — lower left ── */}
        <g transform="translate(40,560)">
          <path d="M0,0 C10,-3 20,0 30,-3 C40,-6 50,-3 60,0" />
          <path d="M0,0 C5,5 0,10 7,16" />
          <path d="M60,0 C55,5 60,10 53,16" />
        </g>

        {/* ── Pearl string — flows diagonally across lower half ── */}
        <path d="M10,630 Q85,620 160,636 Q235,651 310,638 Q325,634 340,636" />
        {Array.from({ length: 14 }, (_, i) => ({
          x: 14 + i * 24,
          y: 630 + Math.sin(i * 0.9) * 4,
        })).map(({ x, y }, i) => (
          <circle key={i} cx={x} cy={y} r="3.5" />
        ))}

        {/* ── Sparkle — lower right ── */}
        <g transform="translate(315,700)">
          <line x1="0" y1="-7" x2="0" y2="7" />
          <line x1="-7" y1="0" x2="7" y2="0" />
          <line x1="-3.5" y1="-3.5" x2="3.5" y2="3.5" />
          <line x1="3.5" y1="-3.5" x2="-3.5" y2="3.5" />
        </g>

        {/* ── Bracelet chain — bottom ── */}
        <path d="M10,770 C60,760 110,775 160,768 C210,761 260,775 330,768" />
        {[20, 55, 90, 125, 160, 195, 230, 270, 310].map((cx, i) => {
          const cy = 770 + (i % 2 === 0 ? -2 : 2);
          return (
            <ellipse key={cx} cx={cx} cy={cy} rx="9" ry="3"
              transform={`rotate(${i % 2 === 0 ? -5 : 5},${cx},${cy})`} />
          );
        })}

      </g>
    </svg>
  );
}
