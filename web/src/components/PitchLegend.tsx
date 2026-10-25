const STRIP = "#2F6B3A"

export default function PitchLegend() {
  return (
    <div className="pitch-legend" aria-label="Pitch diagram legend">
      <div className="legend-item">
        <svg width="36" height="12" viewBox="0 0 36 12" aria-hidden="true">
          <rect width="36" height="12" rx="2" fill={STRIP} />
          <line x1="4" y1="6" x2="32" y2="6" stroke="#F2F5EE" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span>Pass played</span>
      </div>
      <div className="legend-item">
        <svg width="36" height="12" viewBox="0 0 36 12" aria-hidden="true">
          <rect width="36" height="12" rx="2" fill={STRIP} />
          <line x1="4" y1="6" x2="32" y2="6" stroke="#BFE8FF" strokeWidth="2"
            strokeDasharray="4 3" strokeLinecap="round" />
        </svg>
        <span>Ghost pass (better option)</span>
      </div>
      <div className="legend-item">
        <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
          <rect width="20" height="20" rx="2" fill={STRIP} />
          <circle cx="10" cy="10" r="3.5" fill="#E3A52B" stroke="#0f1923" strokeWidth="0.5" />
          <text x="10" y="11.1" fontSize="2.8" textAnchor="middle"
            fill="#0f1923" fontWeight="700" fontFamily="Arial Narrow, sans-serif">7</text>
          <circle cx="10" cy="10" r="5.5" fill="none" stroke="#F2F5EE" strokeWidth="0.7" opacity="0.75" />
        </svg>
        <span>Nearest defenders</span>
      </div>
    </div>
  )
}
