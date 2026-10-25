interface LogoProps { size?: number }

export default function Logo({ size = 24 }: LogoProps) {
  const h = Math.round(size * 20 / 28)
  return (
    <svg viewBox="0 0 28 20" width={size} height={h} aria-hidden="true">
      <line x1="2" y1="14" x2="10" y2="10.5"
            stroke="#BFE8FF" strokeWidth="1.5" strokeDasharray="1.5 2" strokeLinecap="round"/>
      <circle cx="18.5" cy="10.5" r="7" fill="#1a2633" stroke="#F2F5EE" strokeWidth="0.8"/>
      <polygon points="18.5,6.2 21.5,8.5 20.4,12 16.6,12 15.5,8.5"
               fill="#0f1923" stroke="#F2F5EE" strokeWidth="0.4"/>
    </svg>
  )
}
