import { RunReplayView } from "@/components/RunReplayView";

export default async function RunReplayPage(
  props: PageProps<"/historial/[runId]/replay">,
) {
  const { runId } = await props.params;
  return <RunReplayView runId={runId} />;
}
