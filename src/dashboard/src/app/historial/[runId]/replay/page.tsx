import { redirect } from "next/navigation";

/** Replay lives inside the control view now. */
export default async function RunReplayPage(
  props: PageProps<"/historial/[runId]/replay">,
) {
  const { runId } = await props.params;
  redirect(`/historial/${runId}`);
}
