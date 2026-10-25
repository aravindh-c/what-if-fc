const STRIP = "#2F6B3A"

export default function PitchLegend() {
  return (
    <div className="pitch-legend" aria-label="Pitch diagram legend">
      <div className="legend-item">
        <svg width="36" height="14" viewBox="0 0 36 14" aria-hidden="true">
          <rect width="36" height="14" rx="2" fill={STRIP} />
          <line x1="4" y1="7" x2="32" y2="7" stroke="#F2F5EE" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span>Pass played</span>
      </div>
      <div className="legend-item">
        <svg width="36" height="14" viewBox="0 0 36 14" aria-hidden="true">
          <defs>
            <filter id="lglow">
              <feGaussianBlur stdDeviation="0.7" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <rect width="36" height="14" rx="2" fill={STRIP} />
          <line x1="4" y1="7" x2="32" y2="7" stroke="#BFE8FF" strokeWidth="1.5"
            strokeDasharray="4 2.5" strokeLinecap="round" filter="url(#lglow)" />
        </svg>
        <span>Ghost pass (better option)</span>
      </div>
      <div className="legend-item">
        <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
          <rect width="22" height="22" rx="2" fill={STRIP} />
          {/* player counter */}
          <circle cx="11" cy="11" r="3.5" fill="#E3A52B" stroke="#0f1923" strokeWidth="0.5" />
          <text x="11" y="12.1" fontSize="2.8" textAnchor="middle"
            fill="#0f1923" fontWeight="700" fontFamily="Arial Narrow, sans-serif">7</text>
          {/* defender ring */}
          <circle cx="11" cy="11" r="5.5" fill="none" stroke="#F2F5EE" strokeWidth="0.7" opacity="0.75" />
        </svg>
        <span>Nearest defenders</span>
      </div>
    </div>
  )
}
