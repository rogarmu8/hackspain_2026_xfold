import type { CSSProperties } from "react";
import { Button } from "@/components/ui/button";

export function FontSampleCard({
  name,
  tag,
  note,
  sansClassName,
  monoClassName,
  monoAsRecursive = false,
}: {
  name: string;
  tag: string;
  note: string;
  sansClassName: string;
  monoClassName: string;
  monoAsRecursive?: boolean;
}) {
  const monoStyle = monoAsRecursive
    ? ({ fontVariationSettings: '"MONO" 1' } as const)
    : undefined;

  return (
    <article
      className={`flex flex-col border border-border bg-card ${sansClassName}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight">{name}</h2>
            <span className="rounded-[4px] bg-active-surface px-2 py-0.5 text-[12px] font-semibold text-active-ink">
              {tag}
            </span>
          </div>
          <p className="mt-1 text-[13px] text-muted-foreground">{note}</p>
        </div>
      </div>

      {/* Mini control chrome */}
      <div className="flex flex-1 flex-col gap-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-[22px] font-semibold tracking-[-0.02em]">
              Control room
            </h3>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              OpenArm cell · press · ninja fold · chute → bag
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-[4px] bg-active-surface px-2 py-1 text-[13px] text-active-ink">
              <span className="size-2 rounded-full bg-active" aria-hidden />
              Sample data
            </span>
            <Button type="button" tabIndex={-1}>
              New experiment
            </Button>
          </div>
        </div>

        {/* Viewport strip */}
        <div className="border border-border bg-viewport text-[#faf6ec]">
          <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
            <span
              className={`text-sm font-semibold tabular ${monoClassName}`}
              style={monoStyle}
            >
              RUN-014 · Seed 42
            </span>
            <span className="text-[11px] tracking-wide text-white/50 uppercase">
              Telemetry without image
            </span>
          </div>
          <dl className="grid grid-cols-2 gap-3 px-3 py-4 sm:grid-cols-5">
            <Metric
              label="Stage"
              value="Ninja fold"
              monoClassName={monoClassName}
              monoStyle={monoStyle}
              mono={false}
            />
            <Metric
              label="Cycle"
              value="14"
              monoClassName={monoClassName}
              monoStyle={monoStyle}
            />
            <Metric
              label="Flatness"
              value="0.002 m"
              monoClassName={monoClassName}
              monoStyle={monoStyle}
            />
            <Metric
              label="In bag"
              value="no"
              monoClassName={monoClassName}
              monoStyle={monoStyle}
              mono={false}
            />
            <Metric
              label="t sim"
              value="28.4 s"
              monoClassName={monoClassName}
              monoStyle={monoStyle}
            />
          </dl>
        </div>

        {/* Stages + data row */}
        <div className="grid gap-3 sm:grid-cols-3">
          {["Pick", "Ninja fold", "Bag"].map((stage, i) => (
            <div
              key={stage}
              className={`rounded-[4px] border px-3 py-2 ${
                i === 1
                  ? "border-active bg-active-surface text-active-ink"
                  : "border-border"
              }`}
            >
              <p className="text-[13px] font-semibold">{stage}</p>
              <p
                className={`mt-0.5 text-[12px] text-muted-foreground tabular ${monoClassName}`}
                style={monoStyle}
              >
                {i === 1 ? "In progress" : i === 0 ? "6.4 s" : "Pending"}
              </p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-baseline justify-between gap-2 border-t border-border pt-3 text-sm">
          <p>
            Batch{" "}
            <span className={`font-semibold tabular ${monoClassName}`} style={monoStyle}>
              B-008
            </span>
            <span className="text-muted-foreground">
              {" "}
              · 12/20 finished · success{" "}
            </span>
            <span className={`tabular ${monoClassName}`} style={monoStyle}>
              83.3 %
            </span>
          </p>
          <p
            className={`text-[13px] text-muted-foreground tabular ${monoClassName}`}
            style={monoStyle}
          >
            Il1 O0 · RUN-014
          </p>
        </div>

        {/* Alphabet specimen */}
        <div className="rounded-[4px] bg-muted/40 px-3 py-2 text-[13px] leading-relaxed">
          <p>Aa Bb Cc · XFOLD OpenArm ninja fold</p>
          <p
            className={`mt-1 tabular ${monoClassName}`}
            style={monoStyle}
          >
            ABCDEF 0123456789 · flatness 0.002 · shirt_in_bag
          </p>
        </div>
      </div>
    </article>
  );
}

function Metric({
  label,
  value,
  monoClassName,
  monoStyle,
  mono = true,
}: {
  label: string;
  value: string;
  monoClassName: string;
  monoStyle?: CSSProperties;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] tracking-wide text-white/50 uppercase">
        {label}
      </dt>
      <dd
        className={`mt-0.5 text-sm ${mono ? `tabular ${monoClassName}` : ""}`}
        style={mono ? monoStyle : undefined}
      >
        {value}
      </dd>
    </div>
  );
}
