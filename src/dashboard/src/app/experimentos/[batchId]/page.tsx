import { BatchDetailView } from "@/components/BatchDetailView";

export default async function BatchPage(props: PageProps<"/experimentos/[batchId]">) {
  const { batchId } = await props.params;
  return <BatchDetailView batchId={batchId} />;
}
