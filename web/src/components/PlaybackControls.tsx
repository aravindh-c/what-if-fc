interface PlaybackControlsProps {
  playing: boolean
  speed: number
  onToggle: () => void
  onSpeed: (s: number) => void
}

const SPEEDS = [10, 30, 60]

function IconPlay() {
  return (
    <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor" aria-hidden="true">
      <path d="M0 0L10 6L0 12z" />
    </svg>
  )
}

function IconPause() {
  return (
    <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor" aria-hidden="true">
      <rect x="0" y="0" width="3.5" height="12" />
      <rect x="6.5" y="0" width="3.5" height="12" />
    </svg>
  )
}

export default function PlaybackControls({ playing, speed, onToggle, onSpeed }: PlaybackControlsProps) {
  return (
    <div className="controls" role="group" aria-label="Playback controls">
      <button
        className="btn btn-primary"
        onClick={onToggle}
        aria-label={playing ? 'Pause' : 'Play'}
        aria-pressed={playing}
      >
        {playing ? <IconPause /> : <IconPlay />}
      </button>
      <div className="speed-btns" role="group" aria-label="Playback speed">
        {SPEEDS.map(s => (
          <button
            key={s}
            className={`btn speed-btn${speed === s ? ' active' : ''}`}
            onClick={() => onSpeed(s)}
            aria-pressed={speed === s}
            aria-label={`${s}× speed`}
          >
            {s}×
          </button>
        ))}
      </div>
    </div>
  )
}
