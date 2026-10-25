function StreamIcon() {
  return (
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" className="how-step-icon">
      <rect width="32" height="32" rx="4" fill="var(--surface-raised)"/>
      <circle cx="16" cy="16" r="3.5" fill="var(--home-color)"/>
      <circle cx="16" cy="16" r="7" fill="none" stroke="var(--home-color)" strokeWidth="1.5" opacity="0.5"/>
      <circle cx="16" cy="16" r="11" fill="none" stroke="var(--home-color)" strokeWidth="1" opacity="0.22"/>
    </svg>
  )
}

function ScoreIcon() {
  return (
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" className="how-step-icon">
      <rect width="32" height="32" rx="4" fill="var(--surface-raised)"/>
      <text x="5" y="14" fontSize="8" fill="var(--home-color)"
            fontFamily="var(--font-display)" fontWeight="700">T+P</text>
      <text x="5" y="23" fontSize="8" fill="var(--home-color)"
            fontFamily="var(--font-display)" fontWeight="700">+F+R</text>
      <line x1="5" y1="26" x2="27" y2="26" stroke="var(--border)" strokeWidth="0.8"/>
    </svg>
  )
}

function AgentsIcon() {
  return (
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" className="how-step-icon">
      <rect width="32" height="32" rx="4" fill="var(--surface-raised)"/>
      <rect x="4" y="6" width="15" height="10" rx="3" fill="var(--home-color)" opacity="0.75"/>
      <polygon points="6,16 11,16 6,21" fill="var(--home-color)" opacity="0.75"/>
      <rect x="13" y="16" width="15" height="10" rx="3" fill="var(--ghost-color)" opacity="0.75"/>
      <polygon points="26,26 21,26 26,31" fill="var(--ghost-color)" opacity="0.75"/>
    </svg>
  )
}

function ValidatorIcon() {
  return (
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" className="how-step-icon">
      <rect width="32" height="32" rx="4" fill="var(--surface-raised)"/>
      <path d="M16 4 L27 8 L27 18 Q27 25 16 30 Q5 25 5 18 L5 8 Z"
            fill="none" stroke="var(--home-color)" strokeWidth="1.5"/>
      <polyline points="10,16 14,21 22,11"
                stroke="var(--home-color)" strokeWidth="2" fill="none"
                strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

const STEPS = [
  {
    n: 1, title: 'Fabric streams the match',
    text: 'Synthetic match events flow through Microsoft Fabric Eventstream into a real-time KQL database.',
    Icon: StreamIcon,
  },
  {
    n: 2, title: 'Code scores every pass option',
    text: 'The Tactical Twin ranks every player on the pitch by how threatening, forward, open and safe a pass to them would be.',
    Icon: ScoreIcon,
  },
  {
    n: 3, title: 'Agents explain it in plain words',
    text: 'Two Azure AI agents write the analysis — one for fans, one for analysts — using only the numbers from the evidence packet.',
    Icon: AgentsIcon,
  },
  {
    n: 4, title: 'A validator checks every number',
    text: 'Before the overlay reaches the screen, a validator confirms every claim in the text matches the data.',
    Icon: ValidatorIcon,
  },
]

export default function HowItWorks() {
  return (
    <section className="how-it-works" aria-label="How it works">
      <h2 className="how-heading">How it works</h2>
      <ol className="how-steps" role="list">
        {STEPS.map(({ n, title, text, Icon }) => (
          <li key={n} className="how-step">
            <div className="how-step-top">
              <span className="how-step-n" aria-hidden="true">{n}</span>
              <Icon />
            </div>
            <p className="how-step-title">{title}</p>
            <p className="how-step-text">{text}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
