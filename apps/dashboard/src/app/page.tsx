import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";

export default async function HomePage() {
  const session = await auth().catch(() => null);
  if (session?.user) {
    redirect("/dashboard");
  }
  redirect("/landing");
}
