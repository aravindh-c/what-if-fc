const STRIP_FILL = "#2F6B3A"

export default function PitchLegend() {
  return (
    <div className="pitch-legend" aria-label="Pitch diagram legend">
      <div className="legend-item">
        <svg width="36" height="14" viewBox="0 0 36 14" aria-hidden="true">
          <rect width="36" height="14" rx="2" fill={STRIP_FILL} />
          <line x1="4" y1="7" x2="32" y2="7" stroke="#F2F5EE" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span>Pass played</span>
      </div>
      <div className="legend-item">
        <svg width="36" height="14" viewBox="0 0 36 14" aria-hidden="true">
          <defs>
            <filter id="legend-glow">
              <feGaussianBlur stdDeviation="0.8" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <rect width="36" height="14" rx="2" fill={STRIP_FILL} />
          <line x1="4" y1="7" x2="32" y2="7" stroke="#BFE8FF" strokeWidth="1.5"
            strokeDasharray="4 2.5" strokeLinecap="round" filter="url(#legend-glow)" />
        </svg>
        <span>Ghost Pass (better option)</span>
      </div>
      <div className="legend-item">
        <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
          <rect width="20" height="20" rx="2" fill={STRIP_FILL} />
          <circle cx="10" cy="10" r="4" fill="#888" stroke="#F2F5EE" strokeWidth="1.0" opacity="0.9" />
          <circle cx="10" cy="10" r="6.5" fill="none" stroke="#F2F5EE" strokeWidth="1.2" strokeDasharray="3 2" opacity="0.7" />
        </svg>
        <span>Nearest defenders</span>
      </div>
    </div>
  )
}
