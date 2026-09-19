import { XFoldLoader } from "@/components/XFoldLoader";

export default function Loading() {
  return (
    <div className="flex min-h-[60svh] items-center justify-center">
      <XFoldLoader size={96} showLabel label="Loading screen…" />
    </div>
  );
}
