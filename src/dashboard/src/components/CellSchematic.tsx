import type { PhaseId, PhaseDefinition } from "@xfold/protocol";
import { operatorStepTitle } from "@/lib/format";

/** Schematic only: not rendered physics or live robot poses. */
export function CellSchematic({ stage, stages }: { stage: PhaseId | null; stages?: PhaseDefinition[] }) {
  if (stages?.some((s) => s.label)) {
    return <div className="flex max-w-2xl flex-col gap-4 text-center font-mono text-xs">
      <p>No reconstructable image · phases recorded by the simulation</p>
      <ol className="flex flex-wrap justify-center gap-3">
        {operatorTitles(stages).map((label) => (
          <li key={label} className={label === operatorStepTitle(stage ?? "", stages) ? "text-hud" : "text-hud-dim"}>
            {label}
          </li>
        ))}
      </ol>
    </div>;
  }
  return <svg viewBox="0 0 800 340" className="w-full max-h-[330px]" role="img" aria-label="Cell schematic: infeed, two OpenArm arms, press, and chute into the bag. Not real robot poses.">
    <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="#faf6ec" strokeOpacity=".045" /></pattern></defs>
    <rect width="800" height="340" fill="url(#grid)" />
    <g stroke="#777b72" strokeWidth="1" fill="none">
      <rect x="275" y="75" width="250" height="190" rx="3" />
      <rect x="287" y="88" width="226" height="164" strokeDasharray="4 5" />
      <rect x="66" y="137" width="125" height="100" rx="3" />
      <path d="M525 180h95l45 85h70v-40h-60l-45-70H525" />
      <path d="M192 185h67m-8-5 8 5-8 5" strokeDasharray="4 5" />
    </g>
    <g fill="none" stroke="#b8b9af" strokeWidth="15" strokeLinecap="round" strokeLinejoin="round">
      <path d="M285 30 225 69 246 126 328 157" /><path d="M515 30 576 69 554 126 473 157" />
    </g>
    <g fill="#252925" stroke="#b8b9af" strokeWidth="2">{[[285,30],[225,69],[246,126],[515,30],[576,69],[554,126]].map(([cx,cy])=><circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="12" />)}</g>
    <path d={stage === "FOLD" || stage === "CHUTE" || stage === "BAG" ? "M362 139h78v78h-78z" : "M357 119l-35 19 15 33 20-9v66h86v-66l20 9 15-33-35-19-25 12h-36z"} fill="#35858a" fillOpacity=".4" stroke="#83bbb6" strokeWidth="1.5" />
    <path d="M365 143l70 68m-70 0 70-68" stroke="#83bbb6" strokeOpacity=".3" />
    <g fontFamily="monospace" fontSize="11" fill="#c5c7bc" letterSpacing="2">
      <text x="84" y="263">01 / ROTATE</text><text x="316" y="292">02 / PRESS + FOLD</text><text x="621" y="292">03 / BAG + PACK</text>
      <text x="330" y="35" fill="#83bbb6">OPENARM · L + R</text>
    </g>
  </svg>;
}

function operatorTitles(stages: PhaseDefinition[]): string[] {
  const titles: string[] = [];
  for (const s of stages) {
    const label = operatorStepTitle(s.state, stages);
    if (titles.at(-1) !== label) titles.push(label);
  }
  return titles;
}
