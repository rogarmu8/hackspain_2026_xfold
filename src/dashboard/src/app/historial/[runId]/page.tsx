import { ControlRoom } from "@/components/ControlRoom";

/** Any run opens in the control view: live if active, replay if finished. */
export default async function RunPage(props: PageProps<"/historial/[runId]">) {
  const { runId } = await props.params;
  return <ControlRoom runId={runId} />;
}
