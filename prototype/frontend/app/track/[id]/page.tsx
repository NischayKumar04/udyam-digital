import { Suspense } from "react";
import { Wordmark } from "@/components/Journey";
import Tracker from "@/components/Tracker";

async function TrackedOrder({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Tracker orderId={decodeURIComponent(id)} />;
}

export default function OrderPage({ params }: PageProps<"/track/[id]">) {
  return (
    <div className="mx-auto flex h-dvh w-full max-w-md flex-col">
      <header className="shrink-0 border-b border-line bg-surface px-5 py-4">
        <Wordmark />
      </header>
      <Suspense>
        <TrackedOrder params={params} />
      </Suspense>
    </div>
  );
}
