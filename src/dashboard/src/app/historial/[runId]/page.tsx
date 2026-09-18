import { RunDetailView } from "@/components/RunDetailView";

export default async function RunPage(props: PageProps<"/historial/[runId]">) {
  const { runId } = await props.params;
  return <RunDetailView runId={runId} />;
}
