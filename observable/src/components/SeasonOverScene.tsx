import type {CSSProperties} from "npm:react";
import type {SeasonOverPhase} from "./metrics.js";

const CAPTIONS: Record<SeasonOverPhase, string> = {
  postseason: "Postseason time!",
  offseason: "Offseason baby",
};

/** Deterministic scatter so particles stay put across renders. */
function scatter(count: number, seed: number): number[][] {
  let state = seed;
  const next = () => (state = (state * 16807) % 2147483647) / 2147483647;
  return Array.from({length: count}, () => [next(), next(), next(), next()]);
}

const STARS = scatter(26, 7);
const CONFETTI = scatter(22, 11);
const FLAKES = scatter(44, 23);
const CONFETTI_COLORS = ["#f5c542", "#e23d4f", "#fff6d6", "#c4b5fd"];

function fallStyle(duration: number, delay: number, drift: number): CSSProperties {
  return {
    animationDuration: `${duration}s`,
    animationDelay: `-${delay}s`,
    "--drift": `${drift}px`,
  } as CSSProperties;
}

function Bunting({cx}: {cx: number}) {
  const half = (r: number) => `M${cx - r} 0A${r} ${r} 0 0 0 ${cx + r} 0Z`;
  return (
    <g>
      <path d={half(40)} fill="#c8102e" />
      <path d={half(33)} fill="#fbf7ee" />
      <path d={half(26)} fill="#c8102e" />
      <path d={half(19)} fill="#fbf7ee" />
      <path d={half(13)} fill="#1c2a5e" />
      {[-6, 0, 6].map((dx) => <circle key={dx} cx={cx + dx} cy={dx === 0 ? 7 : 4} r={1.3} fill="#fbf7ee" />)}
    </g>
  );
}

function LightTower({x, lit}: {x: number; lit: boolean}) {
  return (
    <g className="season-over-tower">
      <rect x={x - 3} y={92} width={6} height={190} />
      <rect x={x - 20} y={70} width={40} height={24} rx={3} />
      {[0, 1].flatMap((row) => [0, 1, 2, 3].map((col) => (
        <circle
          key={`${row}-${col}`}
          className={lit ? "season-over-bulb" : "season-over-bulb-off"}
          cx={x - 13.5 + col * 9}
          cy={77 + row * 10}
          r={3}
        />
      )))}
    </g>
  );
}

/** Face-on baseball whose seams bow toward the edges. */
function Baseball({cx, cy, r, id}: {cx: number; cy: number; r: number; id: string}) {
  const k = r / 52;
  const seam = (side: -1 | 1) => {
    const top = `${cx + side * 22 * k} ${cy - 48 * k}`;
    const bottom = `${cx + side * 22 * k} ${cy + 48 * k}`;
    const pull = cx + side * 50 * k;
    return `M${top}C${pull} ${cy - 22 * k} ${pull} ${cy + 22 * k} ${bottom}`;
  };
  return (
    <g>
      <defs>
        <radialGradient id={`${id}-leather`} cx=".38" cy=".34" r=".75">
          <stop offset="0" stopColor="#fffdf7" />
          <stop offset=".7" stopColor="#f3ead8" />
          <stop offset="1" stopColor="#d9ccb1" />
        </radialGradient>
        <clipPath id={`${id}-clip`}><circle cx={cx} cy={cy} r={r} /></clipPath>
      </defs>
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id}-leather)`} />
      <g clipPath={`url(#${id}-clip)`} fill="none" stroke="#c8102e">
        {([-1, 1] as const).map((side) => (
          <g key={side}>
            <path d={seam(side)} strokeWidth={1.4 * k} />
            <path d={seam(side)} strokeWidth={8 * k} strokeDasharray={`${1.5 * k} ${5 * k}`} />
          </g>
        ))}
      </g>
    </g>
  );
}

function PostseasonArt() {
  return (
    <svg className="season-over-art" viewBox="0 0 400 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="po-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#100a2b" />
          <stop offset=".55" stopColor="#2a1660" />
          <stop offset="1" stopColor="#4a1f73" />
        </linearGradient>
        <radialGradient id="po-glow">
          <stop offset="0" stopColor="#ffe9b0" stopOpacity=".5" />
          <stop offset="1" stopColor="#ffe9b0" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="po-beam" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff3c4" stopOpacity=".38" />
          <stop offset="1" stopColor="#fff3c4" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="po-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0d0a22" stopOpacity="0" />
          <stop offset="1" stopColor="#0d0a22" />
        </linearGradient>
      </defs>
      <rect width="400" height="320" fill="url(#po-sky)" />
      {STARS.map(([x, y, size, delay], index) => (
        <circle
          key={index}
          className="season-over-star"
          cx={x * 400}
          cy={20 + y * 170}
          r={0.6 + size * 1.1}
          style={{animationDelay: `-${delay * 4}s`}}
        />
      ))}
      <circle cx="200" cy="135" r="110" fill="url(#po-glow)" />
      <Baseball cx={200} cy={135} r={52} id="po-ball" />
      <g className="season-over-beams">
        <polygon points="26,82 66,82 262,300 138,300" fill="url(#po-beam)" />
        <polygon points="334,82 374,82 262,300 138,300" fill="url(#po-beam)" />
      </g>
      <LightTower x={46} lit />
      <LightTower x={354} lit />
      <path d="M0 252Q200 206 400 252V320H0Z" fill="#0d0a22" />
      <ellipse cx="200" cy="322" rx="214" ry="54" fill="#1d5e36" />
      <polygon points="200,314 246,292 200,270 154,292" fill="#a86a3d" />
      <polygon points="200,306 232,292 200,278 168,292" fill="#23703f" />
      <circle cx="200" cy="292" r="4" fill="#a86a3d" />
      {[[200, 314], [246, 292], [200, 270], [154, 292]].map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x - 2.5} y={y - 2.5} width="5" height="5" fill="#fbf7ee" transform={`rotate(45 ${x} ${y})`} />
      ))}
      <rect y="250" width="400" height="70" fill="url(#po-fade)" />
      {CONFETTI.map(([x, size, duration, delay], index) => (
        <rect
          key={index}
          className="season-over-fall season-over-confetti"
          x={x * 400}
          y={-12}
          width={3 + size * 3}
          height={6 + size * 4}
          rx={1}
          fill={CONFETTI_COLORS[index % CONFETTI_COLORS.length]}
          style={fallStyle(7 + duration * 6, delay * 13, (size - 0.5) * 60)}
        />
      ))}
      <Bunting cx={66} />
      <Bunting cx={200} />
      <Bunting cx={334} />
    </svg>
  );
}

function OffseasonArt() {
  const base = (x: number, y: number) => (
    <g key={`${x}-${y}`}>
      <ellipse cx={x} cy={y + 1} rx={9} ry={3.6} className="season-over-drift" />
      <rect x={x - 3} y={y - 4} width="6" height="6" className="season-over-base" transform={`rotate(45 ${x} ${y - 1})`} />
    </g>
  );
  return (
    <svg className="season-over-art" viewBox="0 0 400 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="off-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style={{stopColor: "var(--snow-sky-top)"}} />
          <stop offset="1" style={{stopColor: "var(--snow-sky-bottom)"}} />
        </linearGradient>
      </defs>
      <rect width="400" height="320" fill="url(#off-sky)" />
      <circle cx="318" cy="62" r="22" className="season-over-sun" />
      <path d="M0 210Q60 196 120 204T250 200T400 206V240H0Z" className="season-over-wall" />
      <LightTower x={46} lit={false} />
      <LightTower x={354} lit={false} />
      <path d="M26 70h40v-3q-20-7-40 0Z" className="season-over-drift" />
      <path d="M334 70h40v-3q-20-7-40 0Z" className="season-over-drift" />
      <path d="M0 228Q200 212 400 228V320H0Z" className="season-over-ground" />
      <polygon points="200,302 306,262 200,232 94,262" className="season-over-chalk" />
      <ellipse cx="200" cy="262" rx="20" ry="6" className="season-over-drift" />
      {[[306, 262], [200, 232], [94, 262], [200, 302]].map(([x, y]) => base(x, y))}
      <Baseball cx={200} cy={170} r={46} id="off-ball" />
      <g className="season-over-beanie">
        <path d="M163 140C160 88 240 88 237 140Z" fill="#6d28d9" />
        <rect x="158" y="131" width="84" height="16" rx="5" fill="#8b5cf6" />
        {Array.from({length: 13}, (_, index) => (
          <line key={index} x1={164 + index * 6} y1="134" x2={164 + index * 6} y2="144" stroke="#6d28d9" strokeWidth="1.6" strokeLinecap="round" />
        ))}
        <circle cx="200" cy="90" r="12" fill="#f1edff" />
        <circle cx="196" cy="86" r="4.5" fill="#ffffff" />
      </g>
      <path d="M112 232C142 206 168 199 200 200C232 199 258 206 288 232Z" className="season-over-ground" />
      {FLAKES.map(([x, size, duration, delay], index) => (
        <circle
          key={index}
          className="season-over-fall season-over-flake"
          cx={x * 400}
          cy={-8}
          r={0.9 + size * 1.9}
          style={fallStyle(9 + duration * 9, delay * 18, (size - 0.4) * 50)}
        />
      ))}
    </svg>
  );
}

export function SeasonOverScene({phase}: {phase: SeasonOverPhase}) {
  return (
    <div className={`season-over season-over-${phase}`}>
      {phase === "postseason" ? <PostseasonArt /> : <OffseasonArt />}
      <div className="season-over-copy">
        <strong>Season's over!</strong>
        <span className="season-over-caption">{CAPTIONS[phase]}</span>
      </div>
    </div>
  );
}
