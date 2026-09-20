"use client";

import { useRouter } from "next/navigation";
import { DicesIcon, PlusIcon } from "lucide-react";
import {
  useId,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import type {
  ClothCondition,
  ClothMix,
  ClothType,
  ClothWeightMap,
  ConditionWeightMap,
  CustomDesignPayload,
} from "@xfold/protocol";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useDashboard } from "@/lib/dashboard-context";
import {
  clothConditionLabel,
  clothTypeLabel,
  DEFAULT_CLOTH_CONDITIONS,
  DEFAULT_CLOTH_TYPES,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { DesignPreview } from "@/components/DesignPreview";
import { cutOutGarment } from "@/lib/garment-cutout";

const WEIGHT_MAX = 10;
const SEED_MAX = 999;
const CONTROL =
  "h-10 rounded-[var(--radius-sm)] border border-input bg-surface px-3 text-sm [background-color:var(--color-surface)]";

function randomSeed(): number {
  return Math.floor(Math.random() * (SEED_MAX + 1));
}

function evenWeights<T extends string>(keys: readonly T[]): Record<T, number> {
  return Object.fromEntries(keys.map((key) => [key, 1])) as Record<T, number>;
}

function weightTotal(weights: Record<string, number>, keys: readonly string[]): number {
  return keys.reduce((sum, key) => sum + Math.max(0, Number(weights[key] ?? 1)), 0);
}

function payloadWeights(
  mix: ClothMix,
  keys: readonly string[],
  weights: Record<string, number>,
): Record<string, number> | undefined {
  if (mix !== "random") return undefined;
  const out: Record<string, number> = {};
  for (const key of keys) out[key] = Math.max(0, Number(weights[key] ?? 1));
  return out;
}

function readDesignFile(file: File): Promise<CustomDesignPayload> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      const comma = text.indexOf(",");
      resolve({
        mime: file.type || "image/png",
        data: comma >= 0 ? text.slice(comma + 1) : text,
      });
    };
    reader.onerror = () => reject(new Error("Could not read the image."));
    reader.readAsDataURL(file);
  });
}

export type NewExperimentDefaults = {
  mode?: "individual" | "batch";
  name?: string;
  seed?: number;
  speed?: number;
  count?: number;
  clothMix?: ClothMix;
  clothTypes?: ClothType[];
  conditionMix?: ClothMix;
  conditions?: ClothCondition[];
  clothTypeWeights?: ClothWeightMap;
  clothConditionWeights?: ConditionWeightMap;
};

type NewExperimentDialogProps = {
  /** Trigger button content. Defaults to “New experiment”. */
  trigger?: ReactNode;
  triggerVariant?: React.ComponentProps<typeof Button>["variant"];
  triggerClassName?: string;
  defaults?: NewExperimentDefaults;
  /** Controlled open (optional). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

function asClothType(value: string | null | undefined): ClothType | undefined {
  return DEFAULT_CLOTH_TYPES.includes(value as ClothType)
    ? (value as ClothType)
    : undefined;
}

function asCondition(value: string | null | undefined): ClothCondition | undefined {
  return DEFAULT_CLOTH_CONDITIONS.includes(value as ClothCondition)
    ? (value as ClothCondition)
    : undefined;
}

export function NewExperimentDialog({
  trigger,
  triggerVariant = "outline",
  triggerClassName,
  defaults,
  open: openProp,
  onOpenChange,
}: NewExperimentDialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = openProp ?? uncontrolledOpen;
  const setOpen = onOpenChange ?? setUncontrolledOpen;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {openProp === undefined ? (
        <DialogTrigger asChild>
          {trigger ?? (
            <Button
              variant={triggerVariant}
              className={cn("h-10 rounded-[var(--radius-sm)] px-3 text-sm font-semibold", triggerClassName)}
            >
              <PlusIcon data-icon="inline-start" />
              New experiment
            </Button>
          )}
        </DialogTrigger>
      ) : null}
      <DialogContent
        className="gap-4 overflow-hidden rounded-[var(--radius-sm)] border border-divider bg-surface p-5 ring-0 sm:max-w-2xl"
        showCloseButton
      >
        {open ? (
          <NewExperimentDialogBody
            key="open"
            defaults={defaults}
            onClose={() => setOpen(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function NewExperimentDialogBody({
  defaults,
  onClose,
}: {
  defaults?: NewExperimentDefaults;
  onClose: () => void;
}) {
  const { launch, snapshot } = useDashboard();
  const router = useRouter();
  const formId = useId();

  const initialCount =
    defaults?.count ?? (defaults?.mode === "batch" ? 5 : 1);
  const [name, setName] = useState(defaults?.name ?? "");
  const [seed, setSeed] = useState(() =>
    defaults?.seed != null ? defaults.seed : randomSeed(),
  );
  // Machinery speed. Fast enough and the garment is left behind, which the
  // line reports as a failed run — that is the experiment.
  const [speed, setSpeed] = useState(defaults?.speed ?? 1);
  const [count, setCount] = useState(initialCount);
  const [clothMix, setClothMix] = useState<ClothMix>(defaults?.clothMix ?? "same");
  const [clothTypes, setClothTypes] = useState<ClothType[]>(
    defaults?.clothTypes?.length ? defaults.clothTypes : ["tee"],
  );
  const [conditionMix, setConditionMix] = useState<ClothMix>(
    defaults?.conditionMix ?? "same",
  );
  const [conditions, setConditions] = useState<ClothCondition[]>(
    defaults?.conditions?.length ? defaults.conditions : ["good"],
  );
  const [clothWeights, setClothWeights] = useState<Record<string, number>>(
    () => ({ ...evenWeights(DEFAULT_CLOTH_TYPES), ...defaults?.clothTypeWeights }),
  );
  const [conditionWeights, setConditionWeights] = useState<Record<string, number>>(
    () => ({
      ...evenWeights(DEFAULT_CLOTH_CONDITIONS),
      ...defaults?.clothConditionWeights,
    }),
  );
  const [designPreview, setDesignPreview] = useState<string | null>(null);
  const [designFile, setDesignFile] = useState<File | null>(null);
  const [designPayload, setDesignPayload] = useState<CustomDesignPayload | null>(null);
  const [designOutline, setDesignOutline] = useState<number[][]>([]);
  const [designAttached, setDesignAttached] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [designInputKey, setDesignInputKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const defaultsKey = [
    defaults?.mode ?? "",
    defaults?.name ?? "",
    defaults?.seed ?? "",
    defaults?.count ?? "",
    defaults?.clothMix ?? "",
    (defaults?.clothTypes ?? []).join(","),
    defaults?.conditionMix ?? "",
    (defaults?.conditions ?? []).join(","),
    JSON.stringify(defaults?.clothTypeWeights ?? {}),
    JSON.stringify(defaults?.clothConditionWeights ?? {}),
  ].join("|");
  const [appliedKey, setAppliedKey] = useState(defaultsKey);
  if (appliedKey !== defaultsKey) {
    setAppliedKey(defaultsKey);
    setName(defaults?.name ?? "");
    setSeed(defaults?.seed != null ? defaults.seed : randomSeed());
    setSpeed(defaults?.speed ?? 1);
    setCount(defaults?.count ?? (defaults?.mode === "batch" ? 5 : 1));
    setClothMix(defaults?.clothMix ?? "same");
    setClothTypes(defaults?.clothTypes?.length ? defaults.clothTypes : ["tee"]);
    setConditionMix(defaults?.conditionMix ?? "same");
    setConditions(defaults?.conditions?.length ? defaults.conditions : ["good"]);
    setClothWeights({
      ...evenWeights(DEFAULT_CLOTH_TYPES),
      ...defaults?.clothTypeWeights,
    });
    setConditionWeights({
      ...evenWeights(DEFAULT_CLOTH_CONDITIONS),
      ...defaults?.clothConditionWeights,
    });
    setDesignPreview(null);
    setDesignFile(null);
    setDesignPayload(null);
    setDesignOutline([]);
    setDesignAttached(false);
    setDesignInputKey((key) => key + 1);
    setError(null);
  }

  const process = snapshot.capabilities.process;
  const scenario = process?.scenario ?? "line";
  const batch = count > 1;
  const canLaunch = batch
    ? snapshot.capabilities.startBatch
    : snapshot.capabilities.startRun;

  const catalogTypes =
    snapshot.capabilities.clothTypes?.length
      ? snapshot.capabilities.clothTypes
          .map((item) => asClothType(item.key))
          .filter((key): key is ClothType => key != null)
      : DEFAULT_CLOTH_TYPES;
  const catalogConditions =
    snapshot.capabilities.clothConditions?.length
      ? snapshot.capabilities.clothConditions
          .map((item) => asCondition(item.key))
          .filter((key): key is ClothCondition => key != null)
      : DEFAULT_CLOTH_CONDITIONS;

  const typePool: ClothType[] = [
    ...(catalogTypes.length ? catalogTypes : DEFAULT_CLOTH_TYPES).filter(
      (key) => key !== "custom",
    ),
    "custom",
  ];
  const catalogPool = typePool.filter((key) => key !== "custom");
  const condPool = catalogConditions.length
    ? catalogConditions
    : DEFAULT_CLOTH_CONDITIONS;
  const selectedType = clothTypes[0] ?? typePool[0] ?? "tee";
  const maxSpeed = snapshot.capabilities.speedRange?.[1] ?? 20;
  const customGarment = clothMix === "same" && selectedType === "custom";

  function summarizeMix(
    mix: ClothMix,
    selected: string[],
    labelOf: (key: string) => string,
    allLabel: string,
  ): string {
    if (mix === "random") return `random (${allLabel}, seed)`;
    if (mix === "list") {
      if (!selected.length) return "empty selection";
      return selected.map(labelOf).join(", ");
    }
    return labelOf(selected[0] ?? "tee");
  }

  function clearDesign() {
    if (designPreview) URL.revokeObjectURL(designPreview);
    setDesignPreview(null);
    setDesignFile(null);
    setDesignPayload(null);
    setDesignOutline([]);
    setDesignAttached(false);
    setDesignInputKey((key) => key + 1);
  }

  async function onPickDesign(file: File | undefined) {
    if (designPreview?.startsWith("blob:")) URL.revokeObjectURL(designPreview);
    setDesignAttached(false);
    setDesignPayload(null);
    setDesignOutline([]);
    if (!file) {
      setDesignPreview(null);
      setDesignFile(null);
      return;
    }
    setDesignFile(file);
    setDetecting(true);
    setError(null);
    try {
      const cut = await cutOutGarment(file);
      setDesignPreview(cut.previewUrl);
      setDesignOutline(cut.outline);
    } catch (err) {
      setDesignPreview(null);
      setDesignFile(null);
      setDesignInputKey((key) => key + 1);
      setError(err instanceof Error ? err.message : "Could not cut out the garment.");
    } finally {
      setDetecting(false);
    }
  }

  async function attachDesign() {
    if (!designFile) {
      setError("Choose an image first.");
      return;
    }
    if (!customGarment) {
      setError("Choose Custom to use a photo as the garment.");
      return;
    }
    setAttaching(true);
    setError(null);
    try {
      setDesignPayload(await readDesignFile(designFile));
      setDesignAttached(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the image.");
    } finally {
      setAttaching(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!canLaunch) {
      setError("The simulator does not expose a launch API yet.");
      return;
    }
    if (!Number.isInteger(count) || count < 1) {
      setError("N runs must be an integer ≥ 1.");
      return;
    }
    if (!Number.isSafeInteger(seed) || seed < 0) {
      setError("Seed must be an integer ≥ 0.");
      return;
    }
    if (clothMix === "same" && !clothTypes[0]) {
      setError("Choose a garment type.");
      return;
    }
    if (clothMix === "list" && clothTypes.length < 1) {
      setError("Select at least one garment type.");
      return;
    }
    if (conditionMix === "same" && !conditions[0]) {
      setError("Choose a condition.");
      return;
    }
    if (conditionMix === "list" && conditions.length < 1) {
      setError("Select at least one condition.");
      return;
    }
    if (clothMix === "random" && weightTotal(clothWeights, catalogPool) <= 0) {
      setError("Raise the weight of at least one garment type.");
      return;
    }
    if (conditionMix === "random" && weightTotal(conditionWeights, condPool) <= 0) {
      setError("Raise the weight of at least one condition.");
      return;
    }
    if (customGarment && !designAttached) {
      setError("Upload the garment photo (or pick another type) before launching.");
      return;
    }
    if (designAttached && !customGarment) {
      setError("Choose Custom to use a photo as the garment.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await Promise.resolve(
        batch
          ? launch({
              mode: "batch",
              name: name.trim(),
              count,
              seedStrategy: "sequential",
              baseSeed: seed,
              scenario,
              clothMix,
              clothTypes: clothMix === "random" ? [] : clothTypes,
              conditionMix,
              conditions: conditionMix === "random" ? [] : conditions,
              clothTypeWeights: payloadWeights(clothMix, catalogPool, clothWeights),
              clothConditionWeights: payloadWeights(
                conditionMix,
                condPool,
                conditionWeights,
              ),
              speed,
              customDesign:
                customGarment && designAttached
                  ? designPayload ?? undefined
                  : undefined,
            })
          : launch({
              mode: "individual",
              name: name.trim(),
              seed,
              scenario,
              clothType: clothMix === "random" ? "random" : clothTypes[0],
              clothCondition:
                conditionMix === "random" ? "random" : conditions[0],
              clothTypeWeights: payloadWeights(clothMix, catalogPool, clothWeights),
              clothConditionWeights: payloadWeights(
                conditionMix,
                condPool,
                conditionWeights,
              ),
              speed,
              customDesign:
                customGarment && designAttached
                  ? designPayload ?? undefined
                  : undefined,
            }),
      );

      if (!result.ok) {
        setError(result.reason);
        return;
      }

      onClose();
      router.push(batch ? "/" : `/historial/${result.id}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle className="text-[17px] font-semibold tracking-[-0.01em]">New experiment</DialogTitle>
        <DialogDescription className="text-[13px]">
          Garment, condition, and how many runs · {process?.scenario ?? "active simulator process"}
        </DialogDescription>
      </DialogHeader>

      {snapshot.connection === "disconnected" || snapshot.provenance === "absent" ? (
        <p className="text-[13px] text-muted-foreground">
          Bridge offline — launch is disabled until the simulator is connected.
        </p>
      ) : null}

      <form id={formId} onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <FieldGroup className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-12">
          <Field className="sm:col-span-4">
            <FieldLabel htmlFor={`${formId}-name`} className="text-[13px] font-semibold">Name</FieldLabel>
            <input
              id={`${formId}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Optional"
              className={`${CONTROL} w-full`}
            />
          </Field>

          <Field className="sm:col-span-2">
            <FieldLabel htmlFor={`${formId}-seed`} className="text-[13px] font-semibold">
              {batch ? "Base seed" : "Seed"}
            </FieldLabel>
            <div className={`${CONTROL} flex items-center gap-1 pr-1.5`}>
              <input
                id={`${formId}-seed`}
                type="number"
                min={0}
                step={1}
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                required
                className="min-w-0 flex-1 bg-transparent outline-none"
              />
              <button
                type="button"
                onClick={() => setSeed(randomSeed())}
                aria-label="Draw a random seed"
                title="Random seed"
                className="inline-flex size-7 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <DicesIcon className="size-3.5" />
              </button>
            </div>
          </Field>

          <Field className="sm:col-span-2">
            <FieldLabel htmlFor={`${formId}-count`} className="text-[13px] font-semibold">Runs</FieldLabel>
            <input
              id={`${formId}-count`}
              type="number"
              min={1}
              value={count}
              onChange={(e) => {
                const next = Number(e.target.value);
                setCount(next);
                if (next <= 1) {
                  if (clothMix === "list") setClothMix("same");
                  if (conditionMix === "list") setConditionMix("same");
                }
              }}
              required
              className={`${CONTROL} w-full`}
            />
          </Field>

          <Field className="sm:col-span-4">
            <FieldLabel htmlFor={`${formId}-speed`} className="text-[13px] font-semibold">Speed</FieldLabel>
            <div className={`${CONTROL} flex items-center gap-2`}>
              <input
                id={`${formId}-speed`}
                type="range"
                min={1}
                max={maxSpeed}
                step={0.5}
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="min-w-0 flex-1 accent-[var(--color-active)]"
              />
              <span className="w-8 shrink-0 text-right font-mono text-[13px] tabular">
                {speed}x
              </span>
            </div>
          </Field>

          <MixField
            className="sm:col-span-6"
            formId={formId}
            axis="garment"
            mix={clothMix}
            onMixChange={(mix) => {
              setClothMix(mix);
              if (mix !== "same") {
                clearDesign();
                if (clothTypes[0] === "custom") setClothTypes(["tee"]);
              }
            }}
            options={typePool}
            selected={clothTypes}
            onSelectedChange={(next) => {
              setClothTypes(next);
              if (next[0] !== "custom") clearDesign();
            }}
            labelOf={clothTypeLabel}
            pickHint="One garment for every run. Custom = cut-out from the photo."
            randomHint="Each run draws a type from the weights and seed."
            weights={clothWeights}
            onWeightChange={(key, value) =>
              setClothWeights((prev) => ({ ...prev, [key]: value }))
            }
          />

          <MixField
            className="sm:col-span-6"
            formId={`${formId}-cond`}
            axis="condition"
            mix={conditionMix}
            onMixChange={setConditionMix}
            options={condPool}
            selected={conditions}
            onSelectedChange={setConditions}
            labelOf={clothConditionLabel}
            pickHint="The same condition for every run."
            randomHint="Each run draws a condition from the weights."
            weights={conditionWeights}
            onWeightChange={(key, value) =>
              setConditionWeights((prev) => ({ ...prev, [key]: value }))
            }
          />

          {customGarment ? (
          <Field className="sm:col-span-12">
            <FieldLabel htmlFor={`${formId}-design`} className="text-[13px] font-semibold">Garment photo</FieldLabel>
            <Input
              key={designInputKey}
              id={`${formId}-design`}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={(event) => void onPickDesign(event.target.files?.[0])}
              className={`${CONTROL} py-1.5`}
            />
            <FieldDescription>
              {detecting
                ? "Detecting the cut-out…"
                : "Plain backdrop, garment centred."}
            </FieldDescription>
            {designPreview ? (
              <div className="mt-2 flex items-start gap-3">
                <div className="w-28 shrink-0">
                  <DesignPreview
                    src={designPreview}
                    outline={designOutline}
                    attached={designAttached}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={attaching || designAttached || detecting}
                    onClick={() => void attachDesign()}
                  >
                    {attaching
                      ? "Uploading…"
                      : designAttached
                        ? "Garment uploaded"
                        : "Upload garment"}
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={clearDesign}>
                    Remove
                  </Button>
                </div>
              </div>
            ) : null}
          </Field>
          ) : null}
        </FieldGroup>

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {!canLaunch ? (
          <p className="text-[13px] text-muted-foreground">
            Launch disabled: connect the XFOLD bridge first.
          </p>
        ) : null}
      </form>

      <DialogFooter className="-mx-5 -mb-5 flex-col items-stretch gap-3 rounded-none border-t border-divider bg-surface px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="min-w-0 text-[13px] text-muted-foreground">
          {count === 1 ? "1 run" : `${count} runs`} · seed {seed} · {speed}x
          {" · "}
          {summarizeMix(clothMix, clothTypes, clothTypeLabel, "catalogue")}
          {" · "}
          {summarizeMix(conditionMix, conditions, clothConditionLabel, "all")}
        </p>
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="outline" className="h-10 rounded-[var(--radius-sm)] px-3 text-sm">
              Cancel
            </Button>
          </DialogClose>
          <Button
            type="submit"
            form={formId}
            variant="outline"
            disabled={submitting || !canLaunch}
            className="h-10 rounded-[var(--radius-sm)] px-3 text-sm font-semibold"
          >
            {submitting ? "Launching…" : "Launch"}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}

const MIX_RANDOM = "__random__";

function MixField<T extends string>({
  formId,
  axis,
  mix,
  onMixChange,
  options,
  selected,
  onSelectedChange,
  labelOf,
  pickHint,
  randomHint,
  weights,
  onWeightChange,
  className,
}: {
  formId: string;
  axis: string;
  mix: ClothMix;
  onMixChange: (mix: ClothMix) => void;
  options: T[];
  selected: T[];
  onSelectedChange: (next: T[]) => void;
  labelOf: (key: string) => string;
  pickHint: string;
  randomHint: string;
  weights: Record<string, number>;
  onWeightChange: (key: T, value: number) => void;
  className?: string;
}) {
  const title = axis === "garment" ? "Garment type" : "Condition";
  const selectId = `${formId}-${axis}`;
  const weightOptions = options.filter((key) => key !== "custom");
  const selectValue =
    mix === "random" ? MIX_RANDOM : (selected[0] ?? options[0] ?? "");

  function onSelect(value: string) {
    if (value === MIX_RANDOM) {
      onMixChange("random");
      return;
    }
    onMixChange("same");
    onSelectedChange([value as T]);
  }

  return (
    <Field
      className={cn(
        "rounded-[var(--radius-sm)] border border-divider bg-card/50 p-3",
        className,
      )}
    >
      <FieldLabel htmlFor={selectId} className="text-[13px] font-semibold">
        {title}
      </FieldLabel>
      <select
        id={selectId}
        className={`${CONTROL} mt-0 w-full`}
        value={selectValue}
        onChange={(e) => onSelect(e.target.value)}
      >
        {options.map((key) => (
          <option key={key} value={key}>
            {labelOf(key)}
          </option>
        ))}
        <option value={MIX_RANDOM}>Random</option>
      </select>

      {mix === "same" ? <FieldDescription>{pickHint}</FieldDescription> : null}

      {mix === "random" ? (
        <>
          <div className="grid grid-cols-1 gap-y-2">
            {weightOptions.map((key) => {
              const value = Math.max(0, Number(weights[key] ?? 1));
              return (
                <label
                  key={key}
                  className="grid grid-cols-[minmax(0,1fr)_minmax(0,5.5rem)_2.25rem] items-center gap-2 text-sm"
                >
                  <span className="min-w-0 truncate">{labelOf(key)}</span>
                  <input
                    type="range"
                    min={0}
                    max={WEIGHT_MAX}
                    step={1}
                    value={value}
                    aria-label={`Weight ${labelOf(key)}`}
                    onChange={(event) =>
                      onWeightChange(key, Number(event.target.value))
                    }
                    className="w-full accent-[var(--color-active)]"
                  />
                  <span className="w-9 shrink-0 text-right font-mono text-[13px] tabular">
                    {value}x
                  </span>
                </label>
              );
            })}
          </div>
          <FieldDescription>
            {randomHint} 0x = never.
          </FieldDescription>
        </>
      ) : null}
    </Field>
  );
}

