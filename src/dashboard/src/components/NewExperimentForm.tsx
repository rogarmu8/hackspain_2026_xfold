"use client";

import Link from "next/link";
import { Input } from "./ui/input";
import { Field, FieldGroup, FieldLabel, FieldDescription } from "./ui/field";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { useDashboard } from "@/lib/dashboard-context";

export function NewExperimentForm() {
  const { launch, snapshot } = useDashboard();
  const router = useRouter();
  const formId = useId();
  const [mode, setMode] = useState<"individual" | "batch">("individual");
  const [name, setName] = useState("");
  const [seed, setSeed] = useState(42);
  const [count, setCount] = useState(5);
  const seedStrategy = "sequential" as const;
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canLaunch =
    mode === "individual"
      ? snapshot.capabilities.startRun
      : snapshot.capabilities.startBatch;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!canLaunch) {
      setError("El simulador aún no expone un API de lanzamiento.");
      return;
    }
    if (mode === "batch" && (!Number.isInteger(count) || count < 1 || count > 100)) {
      setError("La cantidad del batch debe estar entre 1 y 100.");
      return;
    }
    if (!Number.isSafeInteger(seed) || seed < 0) {
      setError("La semilla debe ser un entero ≥ 0.");
      return;
    }

    setSubmitting(true);
    const result =
      mode === "individual"
        ? launch({
            mode: "individual",
            name: name.trim(),
            seed,
            scenario: "openarm-ninja-bag",
          })
        : launch({
            mode: "batch",
            name: name.trim(),
            count,
            seedStrategy,
            baseSeed: seed,
            scenario: "openarm-ninja-bag",
          });

    setSubmitting(false);
    if (!result.ok) {
      setError(result.reason);
      return;
    }

    if (mode === "batch") {
      router.push(`/experimentos/${result.id}`);
    } else {
      router.push(`/historial/${result.id}`);
    }
  }

  return (
    <AppShell
      title="Nuevo experimento"
      description="Individual o batch secuencial · configuración compatible con el escenario OpenArm"
      actions={
        <Button asChild variant="outline"><Link href="/experimentos">Volver</Link></Button>
      }
    >
      {snapshot.provenance === "fixture" ? (
        <p className="mb-4 rounded-[var(--radius-sm)] bg-surface px-3 py-2 text-[13px] text-muted-foreground">
          <span className="font-semibold text-ink">Datos de ejemplo.</span> El
          lanzamiento solo muta el adaptador local; no se envía nada a MuJoCo.
        </p>
      ) : null}

      <form
        id={formId}
        onSubmit={onSubmit}
        className="max-w-xl border border-divider bg-surface p-6"
        noValidate
      >
        <FieldGroup>
          <Field><FieldLabel>Modo de ejecución</FieldLabel>
            <ToggleGroup type="single" variant="outline" value={mode} onValueChange={(value) => { if (value === "individual" || value === "batch") setMode(value); }} aria-label="Modo de ejecución">
              <ToggleGroupItem value="individual">Individual</ToggleGroupItem><ToggleGroupItem value="batch">Batch</ToggleGroupItem>
            </ToggleGroup>
          </Field>
        </FieldGroup>
        <FieldGroup className="mt-6">
          <FormField
            label="Nombre (opcional)"
            htmlFor={`${formId}-name`}
            hint="Visible en Experimentos e Historial."
          >
            <Input
              id={`${formId}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="p. ej. Smoke OpenArm"
            />
          </FormField>

          <FormField
            label={mode === "batch" ? "Semilla base" : "Semilla"}
            htmlFor={`${formId}-seed`}
            hint="Entero ≥ 0. En batch secuencial se incrementa por ejecución."
          >
            <Input
              id={`${formId}-seed`}
              type="number"
              min={0}
              step={1}
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              required
            />
          </FormField>

          {mode === "batch" ? (
            <>
              <FormField
                label="Cantidad de ejecuciones"
                htmlFor={`${formId}-count`}
                hint="MVP: cola secuencial, sin paralelismo garantizado."
              >
                <Input
                  id={`${formId}-count`}
                  type="number"
                  min={1}
                  max={100}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                  required
                />
              </FormField>
              <p className="text-sm text-muted-foreground">Las semillas se asignan consecutivamente desde la semilla base.</p>
            </>
          ) : null}

          <details className="border-t border-divider pt-4">
            <summary className="cursor-pointer text-sm font-semibold">
              Opciones avanzadas
            </summary>
            <p className="mt-3 text-sm text-muted-foreground">
              Escenario fijo: <code className="font-mono">openarm-ninja-bag</code>{" "}
              (PICK → SPREAD → PRESS → FOLD → CHUTE → BAG). No hay más knobs
              cableados al sim todavía.
            </p>
          </details>
        </FieldGroup>

        <div className="mt-6 rounded-[var(--radius-sm)] bg-canvas px-4 py-3 text-sm text-muted-foreground">
          <p className="font-semibold text-ink">Resumen</p>
          <p className="mt-1">
            {mode === "individual"
              ? `1 ejecución · semilla ${seed} · escenario openarm-ninja-bag`
              : `Batch ×${count} · semillas ${seed}… · cola secuencial`}
          </p>
        </div>

        {error ? (
          <p className="mt-4 text-sm text-danger" role="alert">
            {error}
          </p>
        ) : null}

        <div className="mt-6 flex flex-wrap gap-3">
          <Button type="submit" disabled={submitting || !canLaunch}>
            {submitting ? "Lanzando…" : "Lanzar"}
          </Button>
          <Button asChild variant="outline"><Link href="/experimentos">
              Cancelar
            </Link></Button>
        </div>
        {!canLaunch ? (
          <p className="mt-3 text-[13px] text-muted-foreground">
            Lanzamiento deshabilitado: sin API de simulación. Activa el
            adaptador de ejemplo en Control para probar el flujo.
          </p>
        ) : null}
      </form>
    </AppShell>
  );
}

function FormField({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: React.ReactNode }) {
  return <Field><FieldLabel htmlFor={htmlFor}>{label}</FieldLabel>{children}{hint && <FieldDescription>{hint}</FieldDescription>}</Field>;
}
