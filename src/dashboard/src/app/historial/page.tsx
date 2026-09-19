import { redirect } from "next/navigation";

/** The run list is the home page now. */
export default function HistoryPage() {
  redirect("/");
}
