import { SAMPLE_TELEMETRY } from "@xfold/protocol";

export default function Home() {
  const snapshot = SAMPLE_TELEMETRY;

  return (
    <main className="mx-auto flex min-h-full w-full max-w-3xl flex-1 flex-col justify-center gap-8 px-6 py-16">
      <p className="text-sm tracking-[0.2em] text-zinc-500 uppercase">
        Hello world
      </p>
      <div className="space-y-3">
        <h1 className="text-5xl font-semibold tracking-tight">XFOLD</h1>
        <p className="max-w-lg text-lg text-zinc-400">
          Monitor for the shirt press, ninja fold, and bag cell. The sim is
          not wired up yet — this page shows a static sample from{" "}
          <code className="font-mono text-zinc-200">@xfold/protocol</code>.
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-zinc-500 uppercase">State</dt>
          <dd className="mt-1 font-mono text-xl">{snapshot.state}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 uppercase">Cycle</dt>
          <dd className="mt-1 font-mono text-xl">{snapshot.cycle}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 uppercase">Flatness</dt>
          <dd className="mt-1 font-mono text-xl">{snapshot.flatness ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 uppercase">In bag</dt>
          <dd className="mt-1 font-mono text-xl">
            {snapshot.shirt_in_bag ? "yes" : "no"}
          </dd>
        </div>
      </dl>
    </main>
  );
}
