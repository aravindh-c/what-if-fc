interface PlaybackControlsProps {
  playing: boolean
  speed: number
  onToggle: () => void
  onSpeed: (s: number) => void
}

const SPEEDS = [10, 30, 60]

export default function PlaybackControls({ playing, speed, onToggle, onSpeed }: PlaybackControlsProps) {
  return (
    <div className="controls" role="group" aria-label="Playback controls">
      <button
        className="btn btn-primary"
        onClick={onToggle}
        aria-label={playing ? 'Pause' : 'Play'}
        aria-pressed={playing}
      >
        {playing ? '⏸' : '▶'}
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
