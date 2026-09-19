"use client";

import { useRouter } from "next/navigation";
import { PlusIcon } from "lucide-react";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
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
  triggerVariant = "default",
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
            <Button variant={triggerVariant} className={triggerClassName}>
              <PlusIcon data-icon="inline-start" />
              New experiment
            </Button>
          )}
        </DialogTrigger>
      ) : null}
      <DialogContent
        className="max-h-[min(90dvh,44rem)] overflow-y-auto sm:max-w-xl"
        showCloseButton
      >
        <NewExperimentDialogBody
          key={open ? "open" : "closed"}
          defaults={defaults}
          onClose={() => setOpen(false)}
        />
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
  const [seed, setSeed] = useState(defaults?.seed ?? 42);
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
    setSeed(defaults?.seed ?? 42);
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
  const scenario = snapshot.provenance === "fixture" ? "openarm-ninja-bag" : process?.scenario ?? "default";
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
    if (!Number.isInteger(count) || count < 1 || count > 100) {
      setError("The row must have between 1 and 100 shirts.");
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
      setError("Select at least one garment type for the row.");
      return;
    }
    if (conditionMix === "same" && !conditions[0]) {
      setError("Choose a condition.");
      return;
    }
    if (conditionMix === "list" && conditions.length < 1) {
      setError("Select at least one condition for the row.");
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
        <DialogTitle>New experiment</DialogTitle>
        <DialogDescription>
          Garment, condition, and how many shirts in the row · {process?.scenario ?? "active simulator process"}
        </DialogDescription>
      </DialogHeader>

      {snapshot.provenance === "fixture" ? (
        <p className="rounded-[var(--radius-sm)] bg-muted/50 px-3 py-2 text-[13px] text-muted-foreground">
          <span className="font-semibold text-foreground">Sample data.</span>{" "}
          Launch only mutates the local adapter; nothing is sent to MuJoCo.
        </p>
      ) : null}

      <form id={formId} onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`${formId}-name`}>Name (optional)</FieldLabel>
            <Input
              id={`${formId}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Cycle check"
            />
            <FieldDescription>Shown on Runs and History.</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor={`${formId}-seed`}>
              {batch ? "Base seed" : "Seed"}
            </FieldLabel>
            <Input
              id={`${formId}-seed`}
              type="number"
              min={0}
              step={1}
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              required
            />
            <FieldDescription>
              Integer ≥ 0. Draws random garment and condition, and if skewed
              the initial heading (still flat). A fixed clean garment and
              condition does not change the input.
            </FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor={`${formId}-count`}>Shirts in a row</FieldLabel>
            <Input
              id={`${formId}-count`}
              type="number"
              min={1}
              max={100}
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
            />
            <FieldDescription>
              1 shirt = one run. More than one = a queued batch, no
              parallelism.
            </FieldDescription>
          </Field>

          <MixField
            formId={formId}
            axis="garment"
            batch={batch}
            mix={clothMix}
            onMixChange={(mix) => {
              setClothMix(mix);
              if (mix !== "same") {
                clearDesign();
                if (clothTypes[0] === "custom") setClothTypes(["tee"]);
              }
            }}
            options={clothMix === "same" ? typePool : catalogPool}
            selected={clothTypes}
            onSelectedChange={(next) => {
              setClothTypes(next);
              if (next[0] !== "custom") clearDesign();
            }}
            labelOf={clothTypeLabel}
            pickHint="One garment for the whole row. Custom = cut-out from the photo outline."
            randomHint="Each shirt is drawn from the catalogue by the weights and the seed."
            listHint="Each shirt is drawn from the types you mark."
            weights={clothWeights}
            onWeightChange={(key, value) =>
              setClothWeights((prev) => ({ ...prev, [key]: value }))
            }
          />

          {customGarment ? (
          <Field>
            <FieldLabel htmlFor={`${formId}-design`}>Garment photo</FieldLabel>
            <Input
              key={designInputKey}
              id={`${formId}-design`}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={(event) => void onPickDesign(event.target.files?.[0])}
            />
            <FieldDescription>
              {detecting
                ? "Detecting the cut-out…"
                : "Plain backdrop, garment centred. We trace the outline and turn it into the cloth (both faces)."}
            </FieldDescription>
            {designPreview ? (
              <div className="mt-2 flex flex-col gap-2">
                <DesignPreview
                  src={designPreview}
                  outline={designOutline}
                  attached={designAttached}
                />
                <div className="flex flex-wrap gap-2">
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

          <MixField
            formId={`${formId}-cond`}
            axis="condition"
            batch={batch}
            mix={conditionMix}
            onMixChange={setConditionMix}
            options={condPool}
            selected={conditions}
            onSelectedChange={setConditions}
            labelOf={clothConditionLabel}
            pickHint="The same condition for the whole row."
            randomHint="Each shirt draws a condition from the weights. Skewed = flat, rotated with the seed."
            listHint="Each shirt is drawn from the conditions you mark."
            weights={conditionWeights}
            onWeightChange={(key, value) =>
              setConditionWeights((prev) => ({ ...prev, [key]: value }))
            }
          />

          <details className="border-t border-border pt-3">
            <summary className="cursor-pointer text-sm font-semibold">
              Advanced options
            </summary>
            <p className="mt-2 text-sm text-muted-foreground">
              {process?.stages.map((s) => s.label ?? s.state).join(" → ") ?? "Phases and parameters come from the active simulator."}
            </p>
          </details>
        </FieldGroup>

        <div className="rounded-[var(--radius-sm)] bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          <p className="font-semibold text-foreground">Summary</p>
          <p className="mt-1">
            {batch ? `Row ×${count}` : "1 shirt"} · seed {seed} · {scenario}
            {" · "}
            {summarizeMix(clothMix, clothTypes, clothTypeLabel, "catalogue")}
            {" · "}
            {summarizeMix(
              conditionMix,
              conditions,
              clothConditionLabel,
              "all",
            )}
          </p>
        </div>

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {!canLaunch ? (
          <p className="text-[13px] text-muted-foreground">
            Launch disabled: no simulation API. Use the sample adapter in Control to try the flow.
          </p>
        ) : null}
      </form>

      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button
          type="submit"
          form={formId}
          disabled={submitting || !canLaunch}
        >
          {submitting ? "Launching…" : "Launch"}
        </Button>
      </DialogFooter>
    </>
  );
}

function MixField<T extends string>({
  formId,
  axis,
  batch,
  mix,
  onMixChange,
  options,
  selected,
  onSelectedChange,
  labelOf,
  pickHint,
  randomHint,
  listHint,
  weights,
  onWeightChange,
}: {
  formId: string;
  axis: string;
  batch: boolean;
  mix: ClothMix;
  onMixChange: (mix: ClothMix) => void;
  options: T[];
  selected: T[];
  onSelectedChange: (next: T[]) => void;
  labelOf: (key: string) => string;
  pickHint: string;
  randomHint: string;
  listHint: string;
  weights: Record<string, number>;
  onWeightChange: (key: T, value: number) => void;
}) {
  const title = axis === "garment" ? "Garment type" : "Condition";

  function toggle(key: T) {
    onSelectedChange(
      selected.includes(key)
        ? selected.filter((item) => item !== key)
        : [...selected, key],
    );
  }

  return (
    <Field>
      <FieldLabel>{title}</FieldLabel>
      <ToggleGroup
        type="single"
        variant="outline"
        value={mix === "list" && !batch ? "same" : mix}
        onValueChange={(value: string) => {
          if (value === "same" || value === "random" || value === "list") {
            onMixChange(value);
          }
        }}
        aria-label={title}
        className="flex-wrap"
      >
        <ToggleGroupItem value="same">
          {batch ? "Same" : "Pick"}
        </ToggleGroupItem>
        <ToggleGroupItem value="random">Random</ToggleGroupItem>
        {batch ? (
          <ToggleGroupItem value="list">Select</ToggleGroupItem>
        ) : null}
      </ToggleGroup>

      {mix === "same" ? (
        <>
          <select
            id={`${formId}-${axis}`}
            className="mt-1 block h-10 w-full rounded-[var(--radius-sm)] border border-input bg-surface px-3 text-sm"
            value={selected[0] ?? options[0] ?? ""}
            onChange={(e) => onSelectedChange([e.target.value as T])}
          >
            {options.map((key) => (
              <option key={key} value={key}>
                {labelOf(key)}
              </option>
            ))}
          </select>
          <FieldDescription>{pickHint}</FieldDescription>
        </>
      ) : null}

      {mix === "random" ? (
        <>
          <div className="mt-1 flex flex-col gap-1.5">
            {options.map((key) => {
              const value = Math.max(0, Number(weights[key] ?? 1));
              return (
                <label
                  key={key}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 text-sm"
                >
                  <span className="min-w-0 truncate">{labelOf(key)}</span>
                  <span className="flex items-center gap-2">
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
                      className="w-28 accent-foreground"
                    />
                    <span className="w-4 text-right font-mono tabular-nums text-muted-foreground">
                      {value}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
          <FieldDescription>
            {randomHint} 0 = never.
          </FieldDescription>
        </>
      ) : null}

      {mix === "list" && batch ? (
        <>
          <div className="flex flex-wrap gap-1.5">
            {options.map((key) => {
              const on = selected.includes(key);
              return (
                <button
                  key={key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(key)}
                  className={cn(
                    "rounded-lg border px-2.5 py-1.5 text-sm transition-colors",
                    on
                      ? "border-foreground bg-muted font-semibold text-foreground"
                      : "border-input bg-card text-muted-foreground hover:text-foreground",
                  )}
                >
                  {labelOf(key)}
                </button>
              );
            })}
          </div>
          <FieldDescription>{listHint}</FieldDescription>
        </>
      ) : null}
    </Field>
  );
}
