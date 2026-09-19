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

export type NewExperimentDefaults = {
  mode?: "individual" | "batch";
  name?: string;
  seed?: number;
  count?: number;
  clothMix?: ClothMix;
  clothTypes?: ClothType[];
  conditionMix?: ClothMix;
  conditions?: ClothCondition[];
};

type NewExperimentDialogProps = {
  /** Trigger button content. Defaults to “Nuevo experimento”. */
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
              Nuevo experimento
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
    setError(null);
  }

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

  const typePool = catalogTypes.length ? catalogTypes : DEFAULT_CLOTH_TYPES;
  const condPool = catalogConditions.length
    ? catalogConditions
    : DEFAULT_CLOTH_CONDITIONS;

  function summarizeMix(
    mix: ClothMix,
    selected: string[],
    labelOf: (key: string) => string,
    allLabel: string,
  ): string {
    if (mix === "random") return `aleatoria (${allLabel})`;
    if (mix === "list") {
      if (!selected.length) return "selección vacía";
      return selected.map(labelOf).join(", ");
    }
    return labelOf(selected[0] ?? "tee");
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!canLaunch) {
      setError("El simulador aún no expone un API de lanzamiento.");
      return;
    }
    if (!Number.isInteger(count) || count < 1 || count > 100) {
      setError("La fila debe tener entre 1 y 100 camisas.");
      return;
    }
    if (!Number.isSafeInteger(seed) || seed < 0) {
      setError("La semilla debe ser un entero ≥ 0.");
      return;
    }
    if (clothMix === "same" && !clothTypes[0]) {
      setError("Elige un tipo de prenda.");
      return;
    }
    if (clothMix === "list" && clothTypes.length < 1) {
      setError("Selecciona al menos un tipo de prenda para la fila.");
      return;
    }
    if (conditionMix === "same" && !conditions[0]) {
      setError("Elige una condición.");
      return;
    }
    if (conditionMix === "list" && conditions.length < 1) {
      setError("Selecciona al menos una condición para la fila.");
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
              scenario: "openarm-ninja-bag",
              clothMix,
              clothTypes: clothMix === "random" ? [] : clothTypes,
              conditionMix,
              conditions: conditionMix === "random" ? [] : conditions,
            })
          : launch({
              mode: "individual",
              name: name.trim(),
              seed,
              scenario: "openarm-ninja-bag",
              clothType: clothMix === "random" ? "random" : clothTypes[0],
              clothCondition:
                conditionMix === "random" ? "random" : conditions[0],
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
        <DialogTitle>Nuevo experimento</DialogTitle>
        <DialogDescription>
          Prenda, condición y cuántas camisas van en fila · cola secuencial
        </DialogDescription>
      </DialogHeader>

      {snapshot.provenance === "fixture" ? (
        <p className="rounded-[var(--radius-sm)] bg-muted/50 px-3 py-2 text-[13px] text-muted-foreground">
          <span className="font-semibold text-foreground">Datos de ejemplo.</span>{" "}
          El lanzamiento solo muta el adaptador local; no se envía nada a MuJoCo.
        </p>
      ) : null}

      <form id={formId} onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`${formId}-name`}>Nombre (opcional)</FieldLabel>
            <Input
              id={`${formId}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="p. ej. Smoke OpenArm"
            />
            <FieldDescription>Visible en Experimentos e Historial.</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor={`${formId}-seed`}>
              {batch ? "Semilla base" : "Semilla"}
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
              Entero ≥ 0. En una fila se incrementa por camisa y también
              determina los sorteos aleatorios.
            </FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor={`${formId}-count`}>Camisas en fila</FieldLabel>
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
              1 camisa = una ejecución. Más de una = batch en cola, sin
              paralelismo.
            </FieldDescription>
          </Field>

          <MixField
            formId={formId}
            axis="prenda"
            batch={batch}
            mix={clothMix}
            onMixChange={setClothMix}
            options={typePool}
            selected={clothTypes}
            onSelectedChange={setClothTypes}
            labelOf={clothTypeLabel}
            pickHint="Una sola prenda para toda la fila."
            randomHint="Cada camisa sale de todo el catálogo."
            listHint="Cada camisa sale de los tipos marcados."
          />

          <MixField
            formId={`${formId}-cond`}
            axis="condición"
            batch={batch}
            mix={conditionMix}
            onMixChange={setConditionMix}
            options={condPool}
            selected={conditions}
            onSelectedChange={setConditions}
            labelOf={clothConditionLabel}
            pickHint="La misma condición en toda la fila."
            randomHint="Cada camisa sortea buena / rasgada / manchada / torcida."
            listHint="Cada camisa sale de las condiciones marcadas."
          />

          <details className="border-t border-border pt-3">
            <summary className="cursor-pointer text-sm font-semibold">
              Opciones avanzadas
            </summary>
            <p className="mt-2 text-sm text-muted-foreground">
              Escenario fijo:{" "}
              <code className="font-mono">openarm-ninja-bag</code> (PICK →
              SPREAD → PRESS → FOLD → CHUTE → BAG).
            </p>
          </details>
        </FieldGroup>

        <div className="rounded-[var(--radius-sm)] bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          <p className="font-semibold text-foreground">Resumen</p>
          <p className="mt-1">
            {batch ? `Fila ×${count}` : "1 camisa"} · semilla {seed}
            {" · "}
            {summarizeMix(clothMix, clothTypes, clothTypeLabel, "catálogo")}
            {" · "}
            {summarizeMix(
              conditionMix,
              conditions,
              clothConditionLabel,
              "todas",
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
            Lanzamiento deshabilitado: sin API de simulación. Usa el adaptador
            de ejemplo en Control para probar el flujo.
          </p>
        ) : null}
      </form>

      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancelar
          </Button>
        </DialogClose>
        <Button
          type="submit"
          form={formId}
          disabled={submitting || !canLaunch}
        >
          {submitting ? "Lanzando…" : "Lanzar"}
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
}) {
  const title = axis === "prenda" ? "Tipo de prenda" : "Condición";

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
          {batch ? "Misma" : "Elegir"}
        </ToggleGroupItem>
        <ToggleGroupItem value="random">Aleatoria</ToggleGroupItem>
        {batch ? (
          <ToggleGroupItem value="list">Seleccionar</ToggleGroupItem>
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
        <FieldDescription>{randomHint}</FieldDescription>
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
