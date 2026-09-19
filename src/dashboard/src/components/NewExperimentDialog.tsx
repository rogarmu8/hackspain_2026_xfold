"use client";

import { useRouter } from "next/navigation";
import { PlusIcon } from "lucide-react";
import {
  useEffect,
  useId,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
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
import { GARMENT_KIND_LABELS, GARMENT_KINDS, type GarmentKind } from "@xfold/protocol";
import { samplesFor, garmentThumbSrc } from "@/lib/garments";
import { useDashboard } from "@/lib/dashboard-context";

export type NewExperimentDefaults = {
  mode?: "individual" | "batch";
  name?: string;
  seed?: number;
  count?: number;
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
      <DialogContent className="sm:max-w-lg" showCloseButton>
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
  const [mode, setMode] = useState<"individual" | "batch">(
    defaults?.mode ?? "individual",
  );
  const [name, setName] = useState(defaults?.name ?? "");
  const [seed, setSeed] = useState(defaults?.seed ?? 42);
  const [count, setCount] = useState(defaults?.count ?? 5);
  const [garmentKind, setGarmentKind] = useState<GarmentKind>("tshirt");
  const [garmentId, setGarmentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setMode(defaults?.mode ?? "individual");
    setName(defaults?.name ?? "");
    setSeed(defaults?.seed ?? 42);
    setCount(defaults?.count ?? 5);
    setGarmentKind("tshirt");
    setGarmentId(null);
    setError(null);
  }, [defaults?.mode, defaults?.name, defaults?.seed, defaults?.count]);

  const canLaunch =
    mode === "individual"
      ? snapshot.capabilities.startRun
      : snapshot.capabilities.startBatch;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!canLaunch) {
      setError("El simulador aún no expone un API de lanzamiento.");
      return;
    }
    if (
      mode === "batch" &&
      (!Number.isInteger(count) || count < 1 || count > 100)
    ) {
      setError("La cantidad del batch debe estar entre 1 y 100.");
      return;
    }
    if (!Number.isSafeInteger(seed) || seed < 0) {
      setError("La semilla debe ser un entero ≥ 0.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await Promise.resolve(
        mode === "individual"
          ? launch({
              mode: "individual",
              name: name.trim(),
              seed,
              scenario: "openarm-ninja-bag",
              garmentKind,
              garmentId: garmentId ?? samplesFor(garmentKind)[0]?.id ?? null,
            })
          : launch({
              mode: "batch",
              name: name.trim(),
              count,
              seedStrategy: "sequential",
              baseSeed: seed,
              scenario: "openarm-ninja-bag",
              garmentKind,
              garmentId: garmentId ?? samplesFor(garmentKind)[0]?.id ?? null,
            }),
      );

      if (!result.ok) {
        setError(result.reason);
        return;
      }

      onClose();
      // Individual runs open straight in control; batches land on the run list.
      router.push(mode === "individual" ? `/historial/${result.id}` : "/");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Nuevo experimento</DialogTitle>
        <DialogDescription>
          Individual o batch secuencial · escenario OpenArm (ninja fold → bolsa)
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
            <FieldLabel>Modo de ejecución</FieldLabel>
            <ToggleGroup
              type="single"
              variant="outline"
              value={mode}
              onValueChange={(value) => {
                if (value === "individual" || value === "batch") setMode(value);
              }}
              aria-label="Modo de ejecución"
            >
              <ToggleGroupItem value="individual">Individual</ToggleGroupItem>
              <ToggleGroupItem value="batch">Batch</ToggleGroupItem>
            </ToggleGroup>
          </Field>

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
            <FieldLabel>Tipo de prenda</FieldLabel>
            <ToggleGroup
              type="single"
              variant="outline"
              value={garmentKind}
              onValueChange={(value) => {
                if (GARMENT_KINDS.includes(value as GarmentKind)) {
                  setGarmentKind(value as GarmentKind);
                  setGarmentId(null);
                }
              }}
              className="grid w-full grid-cols-3 gap-2"
              aria-label="Tipo de prenda"
            >
              {GARMENT_KINDS.map((kind) => {
                const preview = samplesFor(kind)[0];
                return (
                  <ToggleGroupItem
                    key={kind}
                    value={kind}
                    className="h-auto flex-col gap-1.5 px-2 py-2 data-[state=on]:border-active"
                  >
                    {preview ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={garmentThumbSrc(preview)}
                        alt=""
                        className="h-16 w-full rounded-[var(--radius-sm)] object-cover"
                      />
                    ) : null}
                    <span className="text-xs font-medium">{GARMENT_KIND_LABELS[kind]}</span>
                  </ToggleGroupItem>
                );
              })}
            </ToggleGroup>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {samplesFor(garmentKind).map((sample, index) => {
                const selected =
                  garmentId === sample.id || (garmentId == null && index === 0);
                return (
                  <button
                    key={sample.id}
                    type="button"
                    onClick={() => setGarmentId(sample.id)}
                    className={`overflow-hidden rounded-[var(--radius-sm)] border text-left ${
                      selected ? "border-active ring-1 ring-active" : "border-border"
                    }`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={garmentThumbSrc(sample)}
                      alt={sample.id}
                      className="h-20 w-full object-cover"
                    />
                    <span className="block px-2 py-1 font-mono text-[11px] text-muted-foreground">
                      {sample.id}
                    </span>
                  </button>
                );
              })}
            </div>
            <FieldDescription>
              Fotos en plano (CC0, dataset Grigorev). Se proyectan sobre el flex T de 151 vértices; la física no cambia.
            </FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor={`${formId}-seed`}>
              {mode === "batch" ? "Semilla base" : "Semilla"}
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
              Entero ≥ 0. En batch secuencial se incrementa por ejecución.
            </FieldDescription>
          </Field>

          {mode === "batch" ? (
            <Field>
              <FieldLabel htmlFor={`${formId}-count`}>
                Cantidad de ejecuciones
              </FieldLabel>
              <Input
                id={`${formId}-count`}
                type="number"
                min={1}
                max={100}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                required
              />
              <FieldDescription>
                MVP: cola secuencial, sin paralelismo garantizado.
              </FieldDescription>
            </Field>
          ) : null}

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
            {mode === "individual"
              ? `1 ejecución · ${GARMENT_KIND_LABELS[garmentKind]} · semilla ${seed} · openarm-ninja-bag`
              : `Batch ×${count} · ${GARMENT_KIND_LABELS[garmentKind]} · semillas ${seed}… · cola secuencial`}
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
