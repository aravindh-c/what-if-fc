export default function PitchLegend() {
  return (
    <div className="pitch-legend" aria-label="Pitch diagram legend">
      <div className="legend-item">
        <svg width="28" height="10" viewBox="0 0 28 10" aria-hidden="true">
          <line x1="2" y1="5" x2="26" y2="5" stroke="#F2F5EE" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span>Pass played</span>
      </div>
      <div className="legend-item">
        <svg width="28" height="10" viewBox="0 0 28 10" aria-hidden="true">
          <defs>
            <filter id="legend-glow">
              <feGaussianBlur stdDeviation="0.8" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <line x1="2" y1="5" x2="26" y2="5" stroke="#BFE8FF" strokeWidth="1.5"
            strokeDasharray="4 2.5" strokeLinecap="round" filter="url(#legend-glow)" />
        </svg>
        <span>Ghost Pass (better option)</span>
      </div>
      <div className="legend-item">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="5" fill="none" stroke="#F2F5EE" strokeWidth="1.2" opacity="0.7" />
          <circle cx="8" cy="8" r="3" fill="#666" stroke="#111" strokeWidth="0.5" />
        </svg>
        <span>Nearest defenders</span>
      </div>
    </div>
  )
}
